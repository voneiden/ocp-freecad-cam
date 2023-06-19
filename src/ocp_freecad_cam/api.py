"""
This is the user facing API of ocp_freecad_cam
"""
import logging
from copy import copy
from typing import Literal, Optional

import Path.Log as Log
import PathScripts.PathUtils as PathUtils
from Path.Dressup import DogboneII, Tags
from Path.Tool import Bit, Controller

from ocp_freecad_cam.api_util import (
    AutoUnitKey,
    CompoundSource,
    ShapeSource,
    apply_params,
    extract_plane,
    extract_topods_shapes,
    map_params,
    shape_source_to_compound,
)
from ocp_freecad_cam.common import PlaneSource, PostProcessor
from ocp_freecad_cam.fc_impl import (
    AdaptiveOp,
    DeburrOp,
    Dressup,
    DrillOp,
    EngraveOp,
    FaceOp,
    HelixOp,
    JobImpl,
    Op,
    PocketOp,
    ProfileOp,
)
from ocp_freecad_cam.fc_impl import Stock as StockImpl
from ocp_freecad_cam.fc_impl import StockBase, Surface3DOp, VCarveOp, WaterlineOp

try:
    import cadquery as cq
except ImportError:
    cq = None
try:
    import build123d as b3d
except ImportError:
    b3d = None

logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)
Log._useConsole = False
Log._defaultLogLevel = Log.Level.DEBUG


class Job:
    def __init__(
        self,
        top_plane: PlaneSource,
        model: CompoundSource,
        post_processor: PostProcessor = None,
        units: Literal["metric", "imperial"] = "metric",
        geometry_tolerance=None,
        coolant_mode: Literal["None", "Flood", "Mist"] = "None",
        final_depth_expression="OpFinalDepth",
        start_depth_expression="OpStartDepth",
        step_down_expression="OpToolDiameter",
        clearance_height_expression="OpStockZMax+SetupSheet.ClearanceHeightOffset",
        clearance_height_offset="5.00 mm",
        safe_height_expression="OpStockZMax+SetupSheet.SafeHeightOffset",
        safe_height_offset="3.00 mm",
        stock: StockBase = StockImpl(),
    ):
        model_compounds = extract_topods_shapes(model, compound=True)
        if (model_count := len(model_compounds)) != 1:
            raise ValueError(
                f"Job should be based around a single compound (got {model_count})"
            )

        self.job_impl = JobImpl(
            top=extract_plane(top_plane),
            model=model_compounds[0],
            post_processor=post_processor,
            units=units,
            geometry_tolerance=geometry_tolerance,
            coolant_mode=coolant_mode,
            final_depth_expression=final_depth_expression,
            start_depth_expression=start_depth_expression,
            step_down_expression=step_down_expression,
            clearance_height_expression=clearance_height_expression,
            clearance_height_offset=clearance_height_offset,
            safe_height_expression=safe_height_expression,
            safe_height_offset=safe_height_offset,
            stock=stock,
        )

        self._needs_rebuild = True

    def show(self, force_rebuild=False):
        ais = self.job_impl.show(rebuild=self._needs_rebuild or force_rebuild)
        self._needs_rebuild = False
        return ais

    def to_gcode(self, force_rebuild=False):
        gcode = self.job_impl.to_gcode(rebuild=self._needs_rebuild or force_rebuild)
        self._needs_rebuild = False
        return gcode

    def save_fcstd(self, filename="debug.fcstd", force_rebuild=False):
        rv = self.job_impl.save_fcstd(
            filename, rebuild=self._needs_rebuild or force_rebuild
        )
        self._needs_rebuild = False
        return rv

    def _add_op(self, op: Op):
        new_ops = self.job_impl.ops[:]
        new_ops.append(op)
        new_job = copy(self)
        new_job.job_impl = new_job.job_impl.copy(new_ops)
        new_job._needs_rebuild = True
        return new_job

    def profile(
        self,
        shapes: ShapeSource,
        tool: "Toolbit",
        *,
        side: Literal["out", "in", "mid"] = "out",
        direction: Literal["cw", "ccw"] = "cw",
        handle_multiple_features: Literal[
            "collectively", "individually"
        ] = "collectively",
        offset_extra: float = 0.0,
        circles: bool = False,
        holes: bool = False,
        perimeter: bool = True,
        dressups: list["Dressup"] = None,
        # OP depth
        clearance_height=None,
        final_depth=None,
        safe_height=None,
        start_depth=None,
        step_down=None,
    ):
        """
        2.5D profile operation will operate on faces, wires and edges.

        Edges do not have to form a closed loop, and they do not have to be
        on the same Z-level. See https://wiki.freecad.org/Path_Profile
        for usage notes.

        :param shapes: Shape(s) to perform this OP on
        :param tool: Tool to use in this OP
        :param side: Defines whether cutter radius compensation is applied
            on the inside or the outside of the perimeter (outer wire).
            Irrelevant for open edges.
        :param direction: Defines the direction of travel (clockwise or
            counterclockwise).
        :param handle_multiple_features: Defines whether to combine features
            or handle them as individual sub operations.
        :param offset_extra: Additional offset.
        :param circles: Faces: profile circular holes (inner wires).
        :param holes: Faces: profile non-circular holes (inner wires).
        :param perimeter: Faces: mill the perimeter (outer wire).
        :param dressups: Define dressups to use in this OP. For example
            Tab (tags) or Dogbone.
        """

        use_comp = side != "mid"
        if not use_comp:
            # Side is irrelevant if we're not using cutter radius compensation
            # Set to some valid value
            side = "out"

        op = ProfileOp(
            # Profile settings
            side=side,
            direction=direction,
            handle_multiple_features=handle_multiple_features,
            offset_extra=offset_extra,
            use_comp=use_comp,
            process_circles=circles,
            process_holes=holes,
            process_perimeter=perimeter,
            # Op settings
            tool=tool,
            dressups=dressups or [],
            compound_data=shape_source_to_compound(shapes),
            clearance_height=clearance_height,
            final_depth=final_depth,
            safe_height=safe_height,
            start_depth=start_depth,
            step_down=step_down,
        )
        return self._add_op(op)

    def face(
        self,
        shapes: ShapeSource,
        tool: "Toolbit",
        *,
        finish_depth: float,
        boundary: Literal["boundbox", "face", "perimeter", "stock"],
        clear_edges: bool,
        exclude_raised: bool,
        pattern: Literal["zigzag", "offset", "zigzag_offset", "line", "grid"],
        # OP depth
        clearance_height=None,
        final_depth=None,
        safe_height=None,
        start_depth=None,
        step_down=None,
    ) -> "Job":
        """
        2.5D face operation to clear material from a surface

        :param shapes:
        :param tool:
        :param finish_depth:
        :param boundary:
        :param clear_edges:
        :param exclude_raised:
        :param pattern:
        :param kwargs:
        :return:
        """

        op = FaceOp(
            finish_depth=finish_depth,
            boundary=boundary,
            clear_edges=clear_edges,
            exclude_raised=exclude_raised,
            pattern=pattern,
            tool=tool,
            compound_data=shape_source_to_compound(
                shapes,
            ),
            clearance_height=clearance_height,
            final_depth=final_depth,
            safe_height=safe_height,
            start_depth=start_depth,
            step_down=step_down,
        )
        return self._add_op(op)

    def pocket(
        self,
        shapes: ShapeSource,
        tool: "Toolbit",
        *,
        finish_depth: float = 0,
        pattern: Literal[
            "zigzag", "offset", "zigzag_offset", "line", "grid"
        ] = "zigzag",
        cut_mode: Literal["climb", "conventional"] = "climb",
        extra_offset: float = 0,
        keep_tool_down: bool = False,
        min_travel: bool = False,
        pocket_last_stepover: float = 0,
        start_at: Literal["center", "edge"] = "center",
        step_over: float = 100,
        use_outline: bool = False,
        zigzag_angle: float = 45.0,
        dressups: list[Dressup] = None,
        # OP depth
        clearance_height=None,
        final_depth=None,
        safe_height=None,
        start_depth=None,
        step_down=None,
    ) -> "Job":
        """
        2.5D pocket operation.

        https://wiki.freecad.org/Path_Pocket_Shape

        :param shapes: Shape(s) to perform this OP on.
        :param tool: Tool to use in this OP.
        :param finish_depth: Final pass depth, 0 to disable.
        :param pattern: Pocket tool path pattern.
        :param cut_mode: Climb/Conventional selection.
        :param extra_offset: Offset the operation boundaries.
        :param keep_tool_down: Attempts to avoid unnecessary retractions
        :param min_travel: Use 3D sorting of path
        :param pocket_last_stepover: ?
        :param start_at: Where the pocketing operation starts (inside-out vs
            outside-in)
        :param step_over: Step over by percentage of cutter diameter
        :param use_outline: Use outline of base geometry
        :param zigzag_angle: Valid when zigzagging
        :param dressups: Dressup operations
        :return:
        """

        op = PocketOp(
            finish_depth=finish_depth,
            pattern=pattern,
            cut_mode=cut_mode,
            extra_offset=extra_offset,
            keep_tool_down=keep_tool_down,
            min_travel=min_travel,
            pocket_last_stepover=pocket_last_stepover,
            start_at=start_at,
            step_over=step_over,
            use_outline=use_outline,
            zigzag_angle=zigzag_angle,
            # OP settings
            tool=tool,
            dressups=dressups or [],
            compound_data=shape_source_to_compound(shapes),
            clearance_height=clearance_height,
            final_depth=final_depth,
            safe_height=safe_height,
            start_depth=start_depth,
            step_down=step_down,
        )
        return self._add_op(op)

    def drill(
        self,
        shapes: ShapeSource,
        tool: "Toolbit",
        dwell_time: Optional[float] = None,
        extra_offset: Optional[Literal["none", "1x", "2x"]] = "none",
        peck_depth: Optional[float] = None,
        keep_tool_down: Optional[bool] = False,
        retract_height: Optional[bool] = None,
        chip_break_enabled: Optional[bool] = False,
        # OP depth
        clearance_height=None,
        final_depth=None,
        safe_height=None,
        start_depth=None,
        step_down=None,
    ):
        """
        Drilling OP works at least on circular edges and cylindrical
        faces.

        :param shapes: shapes to perform this op on
        :param tool: tool to use
        :param dwell_time: setting this to any value will enable dwell
        :param extra_offset: extend drilling depth
        :param peck_depth:
        :param keep_tool_down:
        :param retract_height:
        :param chip_break_enabled:
        :return:
        """

        op = DrillOp(
            tool=tool,
            dwell_time=dwell_time,
            extra_offset=extra_offset,
            peck_depth=peck_depth,
            keep_tool_down=keep_tool_down,
            retract_height=retract_height,
            chip_break_enabled=chip_break_enabled,
            compound_data=shape_source_to_compound(shapes),
            clearance_height=clearance_height,
            final_depth=final_depth,
            safe_height=safe_height,
            start_depth=start_depth,
            step_down=step_down,
        )
        return self._add_op(op)

    def helix(
        self,
        shapes: ShapeSource,
        tool: "Toolbit",
        *,
        direction: Optional[Literal["cw", "ccw"]] = "cw",
        offset_extra: Optional[float] = 0,
        start_radius: Optional[float] = 0,
        start_side: Optional[Literal["out", "in"]] = "out",
        step_over: Optional[float] = 50,
        # OP depth
        clearance_height=None,
        final_depth=None,
        safe_height=None,
        start_depth=None,
        step_down=None,
    ):
        """
        Perform a helix plunge.

        :param shapes: circular shapes to perform the op on
        :param tool: tool to use
        :param direction: default clockwise helix
        :param offset_extra: negative value creates a roughing pass followed
            by a final pass with the original radius
        :param start_radius: inner radius?
        :param start_side: define where the op starts when doing multiple passes
        :param step_over: percentage of tool diameter to step over
        :return:
        """

        op = HelixOp(
            direction=direction,
            offset_extra=offset_extra,
            start_radius=start_radius,
            start_side=start_side,
            step_over=step_over,
            # Op
            tool=tool,
            compound_data=shape_source_to_compound(
                shapes,
            ),
            clearance_height=clearance_height,
            final_depth=final_depth,
            safe_height=safe_height,
            start_depth=start_depth,
            step_down=step_down,
        )
        return self._add_op(op)

    def deburr(
        self,
        shapes: ShapeSource,
        tool: "Toolbit",
        *,
        width: float | str = "1 mm",
        extra_depth: float | str = "0.5 mm",
        direction: Literal["cw", "ccw"] = "cw",
        entry_point: int = 0,
        # OP depth
        clearance_height=None,
        final_depth=None,
        safe_height=None,
        start_depth=None,
        step_down=None,
    ):
        op = DeburrOp(
            width=width,
            extra_depth=extra_depth,
            direction=direction,
            entry_point=entry_point,
            # Op
            tool=tool,
            compound_data=shape_source_to_compound(shapes),
            clearance_height=clearance_height,
            final_depth=final_depth,
            safe_height=safe_height,
            start_depth=start_depth,
            step_down=step_down,
        )
        return self._add_op(op)

    def engrave(
        self,
        shapes: ShapeSource,
        tool: "Toolbit",
        *,
        start_vertex: int = 0,
        # OP depth
        clearance_height=None,
        final_depth=None,
        safe_height=None,
        start_depth=None,
        step_down=None,
    ):
        op = EngraveOp(
            start_vertex=start_vertex,
            tool=tool,
            compound_data=shape_source_to_compound(shapes),
            clearance_height=clearance_height,
            final_depth=final_depth,
            safe_height=safe_height,
            start_depth=start_depth,
            step_down=step_down,
        )
        return self._add_op(op)

    def v_carve(
        self,
        shapes: ShapeSource,
        tool: "Toolbit",
        *,
        discretize: float = 0.01,
        colinear: float = 10.0,
        # OP depth
        clearance_height=None,
        final_depth=None,
        safe_height=None,
        start_depth=None,
        step_down=None,
    ):
        """
        V-Carve based on voronoi diagrams.

        Verify the tool path carefully! This algorithm is sometimes
        unstable.

        :param shapes:
        :param tool:
        :param discretize: Try a smaller value if getting too many retracts.
        :param colinear:
        :return:
        """

        op = VCarveOp(
            discretize=discretize,
            colinear=colinear,
            # Op
            tool=tool,
            compound_data=shape_source_to_compound(shapes),
            clearance_height=clearance_height,
            final_depth=final_depth,
            safe_height=safe_height,
            start_depth=start_depth,
            step_down=step_down,
        )
        return self._add_op(op)

    def surface(
        self,
        shapes: Optional[ShapeSource],
        tool: "Toolbit",
        *,
        bound_box: Literal["base_bound_box", "stock"] = "base_bound_box",
        cut_mode: Literal["climb", "conventional"] = "climb",
        cut_pattern: Literal[
            "line", "circular", "circular_zig_zag", "offset", "spiral", "zigzag"
        ] = "line",
        cut_pattern_angle: float = 0,
        cut_pattern_reversed: bool = False,
        depth_offset: float = 0,
        layer_mode: Literal["single", "multi"] = "single",
        profile_edges: Literal["none", "only", "first", "last"] = "none",
        sample_interval: float | str = "1.0 mm",
        step_over: float = 100,
        angular_deflection: float | str = "0.25 mm",
        linear_deflection: float
        | str = "0.001 mm",  # Not visible in UI, but this is the default in code
        circular_use_g2g3: bool = False,
        gap_threshold: float | str = "0.01 mm",
        optimize_linear_paths: bool = True,
        optimize_step_over_transitions: bool = False,
        avoid_last_x_faces: int = 0,
        avoid_last_x_internal_features: bool = True,
        boundary_adjustment: float | str = 0,
        boundary_enforcement: bool = True,
        multiple_features: Literal["collectively", "individually"] = "collectively",
        internal_features_adjustment: float | str = 0,
        internal_features_cut: bool = True,
        start_point: tuple[float | str, float | str, float | str] = None,
        scan_type: Literal["planar", "rotational"] = "planar",
        # OP depth
        clearance_height=None,
        final_depth=None,
        safe_height=None,
        start_depth=None,
        step_down=None,
    ):
        op = Surface3DOp(
            bound_box=bound_box,
            cut_mode=cut_mode,
            cut_pattern=cut_pattern,
            cut_pattern_angle=cut_pattern_angle,
            cut_pattern_reversed=cut_pattern_reversed,
            depth_offset=depth_offset,
            layer_mode=layer_mode,
            profile_edges=profile_edges,
            sample_interval=sample_interval,
            step_over=step_over,
            angular_deflection=angular_deflection,
            linear_deflection=linear_deflection,
            circular_use_g2g3=circular_use_g2g3,
            gap_threshold=gap_threshold,
            optimize_linear_paths=optimize_linear_paths,
            optimize_step_over_transitions=optimize_step_over_transitions,
            avoid_last_x_faces=avoid_last_x_faces,
            avoid_last_x_internal_features=avoid_last_x_internal_features,
            boundary_adjustment=boundary_adjustment,
            boundary_enforcement=boundary_enforcement,
            multiple_features=multiple_features,
            internal_features_adjustment=internal_features_adjustment,
            internal_features_cut=internal_features_cut,
            start_point=start_point,
            scan_type=scan_type,
            # Op
            tool=tool,
            compound_data=shape_source_to_compound(shapes, allow_none=True),
            clearance_height=clearance_height,
            final_depth=final_depth,
            safe_height=safe_height,
            start_depth=start_depth,
            step_down=step_down,
        )
        return self._add_op(op)

    def waterline(
        self,
        shapes: Optional[ShapeSource],
        tool: "Toolbit",
        *,
        algorithm: Literal["ocl", "experimental"] = "ocl",
        bound_box: Literal["base", "stock"] = "base",
        cut_mode: Literal["climb", "conventional"] = "climb",
        depth_offset: float | str = 0,
        layer_mode: Literal["single", "multi"] = "single",
        sample_interval: float | str = "1.00 mm",
        angular_deflection: float | str = "0.25 mm",
        linear_deflection: float | str = "0.01 mm",
        # OP depth
        clearance_height=None,
        final_depth=None,
        safe_height=None,
        start_depth=None,
        step_down=None,
    ):
        op = WaterlineOp(
            algorithm=algorithm,
            bound_box=bound_box,
            cut_mode=cut_mode,
            depth_offset=depth_offset,
            layer_mode=layer_mode,
            sample_interval=sample_interval,
            angular_deflection=angular_deflection,
            linear_deflection=linear_deflection,
            # Op
            tool=tool,
            compound_data=shape_source_to_compound(shapes, allow_none=True),
            clearance_height=clearance_height,
            final_depth=final_depth,
            safe_height=safe_height,
            start_depth=start_depth,
            step_down=step_down,
        )
        return self._add_op(op)

    def adaptive(
        self,
        shapes: Optional[ShapeSource],
        tool: "Toolbit",
        *,
        finishing_profile: bool = True,
        force_inside_cut: bool = False,
        helix_angle: float = 5,
        helix_cone_angle: float = 0,
        helix_diameter_limit: float | str = 0,
        keep_tool_down_ratio: float | str = "3.00 mm",
        lift_distance: float | str = 0,
        operation_type: Literal["clearing", "profiling"] = "clearing",
        side: Literal["in", "out"] = "in",
        step_over: float = 20,
        stock_to_leave: float | str = 0,
        tolerance: float = 0.1,
        use_helix_arcs: bool = False,
        use_outline: bool = False,
        # OP depth
        clearance_height=None,
        final_depth=None,
        safe_height=None,
        start_depth=None,
        step_down=None,
    ):
        op = AdaptiveOp(
            finishing_profile=finishing_profile,
            force_inside_cut=force_inside_cut,
            helix_angle=helix_angle,
            helix_cone_angle=helix_cone_angle,
            helix_diameter_limit=helix_diameter_limit,
            keep_tool_down_ratio=keep_tool_down_ratio,
            lift_distance=lift_distance,
            operation_type=operation_type,
            side=side,
            step_over=step_over,
            stock_to_leave=stock_to_leave,
            tolerance=tolerance,
            use_helix_arcs=use_helix_arcs,
            use_outline=use_outline,
            # Op
            tool=tool,
            compound_data=shape_source_to_compound(
                shapes,
            ),
            clearance_height=clearance_height,
            final_depth=final_depth,
            safe_height=safe_height,
            start_depth=start_depth,
            step_down=step_down,
        )
        return self._add_op(op)


class Toolbit:
    props: dict
    _prop_mapping = {}

    def __init__(self, tool_name: str, tool_file_name: str, tool_number=1, path=None):
        self.tool_name = tool_name
        self.tool_file_name = tool_file_name
        self.tool_number = tool_number
        self.path = path
        self.props = {}
        self.obj = None
        self._tool_controller = None

    def tool_controller(self, fc_job, units):
        if self._tool_controller is None:
            self.create(fc_job, units)
        return self._tool_controller

    def create(self, fc_job, units):
        tool_shape = Bit.findToolShape(self.tool_file_name, self.path)
        if not tool_shape:
            raise ValueError(
                f"Could not find tool {self.tool_file_name} (path: {self.path})"
            )

        self.obj = Bit.Factory.Create(self.tool_name, tool_shape)
        self._tool_controller = Controller.Create(
            f"TC: {self.tool_name}", tool=self.obj, toolNumber=self.tool_number
        )
        fc_job.addToolController(self._tool_controller)
        apply_params(self.obj, self.props, units)


class Endmill(Toolbit):
    _file_name = "endmill.fcstd"
    _prop_mapping = {
        "chip_load": "ChipLoad",
        "flutes": "Flutes",
        "material": "Material",
        "spindle_direction": "SpindleDirection",
        "cutting_edge_height": AutoUnitKey("CuttingEdgeHeight"),
        "diameter": AutoUnitKey("Diameter"),
        "length": AutoUnitKey("Length"),
        "shank_diameter": AutoUnitKey("Shank Diameter"),
    }

    def __init__(
        self,
        tool_name: str = "",
        # Generic
        chip_load=None,
        flutes=None,
        material=None,
        spindle_direction=None,
        # Bit specific
        cutting_edge_height=None,
        diameter=None,
        length=None,
        shank_diameter=None,
        # TC
        tool_number: int = 1,
    ):
        super().__init__(tool_name, self._file_name, tool_number=tool_number)

        self.props = map_params(
            self._prop_mapping,
            chip_load=chip_load,
            flutes=flutes,
            material=material,
            spindle_direction=spindle_direction,
            cutting_edge_height=cutting_edge_height,
            diameter=diameter,
            length=length,
            shank_diameter=shank_diameter,
        )


class Ballnose(Endmill):
    _file_name = "ballnose.fcstd"


class VBit(Endmill):
    _file_name = "v-bit.fcstd"

    _prop_mapping = {
        **Endmill._prop_mapping,
        "tip_angle": "CuttingEdgeAngle",
        "tip_diameter": AutoUnitKey("TipDiameter"),
    }

    def __init__(
        self,
        tool_name: str = "",
        # Generic
        chip_load=None,
        flutes=None,
        material=None,
        spindle_direction=None,
        # Bit specific
        cutting_edge_height=None,
        diameter=None,
        length=None,
        shank_diameter=None,
        tip_angle=None,
        tip_diameter=None,
        # TC
        tool_number: int = 1,
    ):
        super().__init__(tool_name, self._file_name, tool_number=tool_number)
        self.props = map_params(
            self._prop_mapping,
            chip_load=chip_load,
            flutes=flutes,
            material=material,
            spindle_direction=spindle_direction,
            cutting_edge_height=cutting_edge_height,
            diameter=diameter,
            length=length,
            shank_diameter=shank_diameter,
            tip_angle=tip_angle,
            tip_diameter=tip_diameter,
        )


class Chamfer(VBit):
    _file_name = "chamfer.fcstd"


class Drill(Toolbit):
    _file_name = "drill.fcstd"
    _prop_mapping = {
        "chip_load": "ChipLoad",
        "flutes": "Flutes",
        "material": "Material",
        "diameter": AutoUnitKey("Diameter"),
        "length": AutoUnitKey("Length"),
        "tip_angle": AutoUnitKey("TipAngle"),
    }

    def __init__(
        self,
        tool_name: str = "",
        # Bit specific
        diameter=None,
        length=None,
        tip_angle=None,
        # Generic
        chip_load=None,
        flutes=None,
        material=None,
        # TC
        tool_number: int = 1,
    ):
        super().__init__(tool_name, self._file_name, tool_number=tool_number)

        self.props = map_params(
            self._prop_mapping,
            chip_load=chip_load,
            flutes=flutes,
            material=material,
            diameter=diameter,
            length=length,
            tip_angle=tip_angle,
        )


class Probe(Toolbit):
    _file_name = "probe.fcstd"
    _prop_mapping = {
        "diameter": AutoUnitKey("Diameter"),
        "length": AutoUnitKey("Length"),
        "shank_diameter": AutoUnitKey("Shank Diameter"),
    }

    def __init__(
        self,
        tool_name: str = "",
        # Bit specific
        diameter=None,
        length=None,
        shank_diameter=None,
        # TC
        tool_number: int = 1,
    ):
        super().__init__(tool_name, self._file_name, tool_number=tool_number)

        self.props = map_params(
            self._prop_mapping,
            diameter=diameter,
            length=length,
            shank_diameter=shank_diameter,
        )


class SlittingSaw(Toolbit):
    _file_name = "slittingsaw.fcstd"
    _prop_mapping = {
        "blade_thickness": AutoUnitKey("BladeThickness"),
        "cap_diameter": AutoUnitKey("CapDiameter"),
        "cap_height": AutoUnitKey("CapHeight"),
        "diameter": AutoUnitKey("Diameter"),
        "length": AutoUnitKey("Length"),
        "shank_diameter": AutoUnitKey("Shank Diameter"),
    }

    def __init__(
        self,
        tool_name: str = "",
        # Bit specific
        blade_thickness=None,
        cap_diameter=None,
        cap_height=None,
        diameter=None,
        length=None,
        shank_diameter=None,
        # TC
        tool_number: int = 1,
    ):
        super().__init__(tool_name, self._file_name, tool_number=tool_number)

        self.props = map_params(
            self._prop_mapping,
            blade_thickness=blade_thickness,
            cap_diameter=cap_diameter,
            cap_height=cap_height,
            diameter=diameter,
            length=length,
            shank_diameter=shank_diameter,
        )


class Bullnose(Endmill):
    _file_name = "bullnose.fcstd"
    _prop_mapping = {
        **Endmill._prop_mapping,
        "flat_radius": AutoUnitKey("FlatRadius"),
    }

    def __init__(
        self,
        tool_name: str = "",
        # Generic
        chip_load=None,
        flutes=None,
        material=None,
        spindle_direction=None,
        # Bit specific
        cutting_edge_height=None,
        diameter=None,
        length=None,
        shank_diameter=None,
        flat_radius=None,
        # TC
        tool_number: int = 1,
    ):
        super().__init__(tool_name, self._file_name, tool_number=tool_number)
        self.props = map_params(
            self._prop_mapping,
            chip_load=chip_load,
            flutes=flutes,
            material=material,
            spindle_direction=spindle_direction,
            cutting_edge_height=cutting_edge_height,
            diameter=diameter,
            length=length,
            shank_diameter=shank_diameter,
            flat_radius=flat_radius,
        )


class ThreadMill(Toolbit):
    _file_name = "bullnose.fcstd"
    _prop_mapping = {
        "chip_load": "ChipLoad",
        "flutes": "Flutes",
        "material": "Material",
        "crest": AutoUnitKey("Crest"),
        "diameter": AutoUnitKey("Diameter"),
        "length": AutoUnitKey("Length"),
        "neck_diameter": AutoUnitKey("NeckDiameter"),
        "neck_length": AutoUnitKey("NeckLength"),
        "shank_diameter": AutoUnitKey("ShankDiameter"),
        "cutting_angle": "cuttingAngle",
    }

    def __init__(
        self,
        tool_name: str = "",
        # Generic
        chip_load=None,
        flutes=None,
        material=None,
        spindle_direction=None,
        # Bit specific
        crest=None,
        diameter=None,
        length=None,
        neck_diameter=None,
        neck_length=None,
        shank_diameter=None,
        cutting_angle=None,
        # TC
        tool_number: int = 1,
    ):
        super().__init__(tool_name, self._file_name, tool_number=tool_number)
        self.props = map_params(
            self._prop_mapping,
            chip_load=chip_load,
            flutes=flutes,
            material=material,
            spindle_direction=spindle_direction,
            crest=crest,
            diameter=diameter,
            length=length,
            neck_diameter=neck_diameter,
            neck_length=neck_length,
            shank_diameter=shank_diameter,
            cutting_angle=cutting_angle,
        )


class Dogbone(Dressup):
    factory = DogboneII
    mapping = {
        "incision": "Incision",
        "custom": "Custom",
        "side": "Side",
        "style": (
            "Style",
            {
                "dogbone": "Dogbone",
                "thor": "T-bone horizontal",
                "tver": "T-bone vertical",
                "tlong": "T-bone long edge",
                "tshort": "T-bone short edge",
            },
        ),
    }

    def __init__(
        self,
        incision: Optional[Literal["adaptive", "fixed", "custom"]] = None,
        custom: Optional[float] = None,
        side: Optional[Literal["left", "right"]] = None,
        style: Optional[Literal["dogbone", "thor", "tver", "tlong", "tshort"]] = None,
    ):
        self.params = map_params(
            self.mapping, incision=incision, custom=custom, side=side, style=style
        )

    def create(self, base):
        # DogboneII has this required code that exists only on the GUI side
        fc_obj = super().create(base)
        job = PathUtils.findParentJob(base)
        job.Proxy.addOperation(fc_obj, base)
        return fc_obj


class Tab(Dressup):
    factory = Tags
    mapping = {
        "angle": "Angle",
        "height": AutoUnitKey("Height"),
        "width": AutoUnitKey("Width"),
        "positions": "Positions",
        "disabled": "Disabled",
        "fillet_radius": "Radius",
        "segmentation_factor": "SegmentationFactor",
    }

    def __init__(
        self,
        angle=None,
        height=None,
        width=None,
        positions=None,
        disabled=None,
        fillet_radius=None,
        segmentation_factor=None,
    ):
        self.params = map_params(
            self.mapping,
            angle=angle,
            height=height,
            width=width,
            positions=positions,
            disabled=disabled,
            fillet_radius=fillet_radius,
            segmentation_factor=segmentation_factor,
        )


Stock = StockImpl
