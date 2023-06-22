"""
This is the user facing API of ocp_freecad_cam
"""
import logging
import os
from copy import copy
from typing import Literal, Optional

import Path.Log as Log
import PathScripts.PathUtils as PathUtils
from Path.Dressup import DogboneII, Tags

from ocp_freecad_cam.api_tool import Toolbit
from ocp_freecad_cam.api_util import (
    AutoUnitKey,
    CompoundSource,
    ShapeSource,
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
logging.getLogger().setLevel(logging.INFO)

if os.environ.get("DEBUG", False):
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
        coolant: Literal["None", "Flood", "Mist"] = "None",
        final_depth_expression="OpFinalDepth",
        start_depth_expression="OpStartDepth",
        step_down_expression="OpToolDiameter",
        clearance_height_expression="OpStockZMax+SetupSheet.ClearanceHeightOffset",
        clearance_height_offset="5.00 mm",
        safe_height_expression="OpStockZMax+SetupSheet.SafeHeightOffset",
        safe_height_offset="3.00 mm",
        stock: StockBase = StockImpl(),
    ):
        """
        Job is the starting point for all CAM operations. It takes a top plane
        as a zero reference (center of the plane is X = Y = Z = 0) and a whole
        model (solid or compound) for the purposes of stock size calculation.

        Additionally, it is possible to override defaults of FreeCAD job, Stock
        and SetupSheet attributes.

        :param top_plane: The zero reference for the job
        :param model: Model for determining the stock size. Also, 3D ops use
            the whole model unless otherwise specified.
        :param post_processor: Postprocessor for the G-Code output.
        :param units: Units of the shapes and g-code output,
            metric (mm) or imperial (in).
        :param geometry_tolerance: smaller increases accuracy, but slows
            down computation.
        :param coolant: default coolant mode for the job
        :param final_depth_expression: custom expression for calculating  the
            default final (bottom) depth
        :param start_depth_expression:custom expression for calculating the
            default start (top) depth
        :param step_down_expression: custom expression for calculating the
            default stepdown, default is tool diameter
        :param clearance_height_expression: custom expression for calculating
            the default clearance height
        :param clearance_height_offset: add or remove a default offset to
            clearance height
        :param safe_height_expression: custom expression for calculating
            the default safe (rapid) height
        :param safe_height_offset: add or remove a default offset to safe
            height
        :param stock: Used to generate the job stock
        """
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
            coolant=coolant,
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

    def show(self, show_object=None, force_rebuild=False):
        """
        Generates an AIS_InteractiveObject that can be used to display
        the result in cq-editor or cq-viewer

        :param show_object:
        :param force_rebuild: set to True if you've tweaked some parameters
            outside the normal fluent flow
        :return: AIS_InteractiveObject that can be given to show_object
        """
        ais = self.job_impl.show(
            show_object=show_object, rebuild=self._needs_rebuild or force_rebuild
        )
        self._needs_rebuild = False
        return ais

    def to_gcode(self, force_rebuild=False):
        """
        Generates G-Code.

        Output is generated by the job's postprocessor and in the job's units.

        :param force_rebuild: set to True if you've tweaked some parameters
            outside the normal fluent flow
        :return:
        """
        gcode = self.job_impl.to_gcode(rebuild=self._needs_rebuild or force_rebuild)
        self._needs_rebuild = False
        return gcode

    def save_fcstd(self, filename="debug.fcstd", force_rebuild=False):
        """
        Save the current document so that it can be opened manually in
        FreeCAD.

        :param filename: Filename to save to (relative to current dir)
        :param force_rebuild: set to True if you've tweaked some parameters
            outside the normal fluent flow
        :return:
        """
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
        coolant: Literal["None", "Flood", "Mist"] = "None",
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
            coolant=coolant,
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
        coolant: Literal["None", "Flood", "Mist"] = "None",
    ) -> "Job":
        """
        2.5D face operation to clear material from a surface.

        See https://wiki.freecad.org/Path_MillFace for usage notes.

        :param shapes: Shape(s) to perform this OP on
        :param tool: Tool to use in this OP
        :param finish_depth:
        :param boundary:
        :param clear_edges:
        :param exclude_raised:
        :param pattern:
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
            coolant=coolant,
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
        coolant: Literal["None", "Flood", "Mist"] = "None",
    ) -> "Job":
        """
        2.5D pocket operation.

        See https://wiki.freecad.org/Path_Pocket_Shape for usage notes.

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
            coolant=coolant,
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
        coolant: Literal["None", "Flood", "Mist"] = "None",
    ):
        """
        Drilling OP works at least on circular edges and cylindrical
        faces.

        See https://wiki.freecad.org/Path_Drilling for usage notes.

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
            coolant=coolant,
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
        coolant: Literal["None", "Flood", "Mist"] = "None",
    ):
        """
        Perform a helix plunge.

        See https://wiki.freecad.org/Path_Helix for usage notes.

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
            coolant=coolant,
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
        coolant: Literal["None", "Flood", "Mist"] = "None",
    ):
        """
        Deburring operation, typically using a chamfer tool.

        See https://wiki.freecad.org/Path_Deburr for usage notes.

        :param shapes:
        :param tool:
        :param width:
        :param extra_depth:
        :param direction:
        :param entry_point:
        :param clearance_height:
        :param final_depth:
        :param safe_height:
        :param start_depth:
        :param step_down:
        :return:
        """
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
            coolant=coolant,
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
        coolant: Literal["None", "Flood", "Mist"] = "None",
    ):
        """
        Engraving OP follows edges.

        See https://wiki.freecad.org/Path_Engrave for usage notes.

        :param shapes:
        :param tool:
        :param start_vertex:
        :param clearance_height:
        :param final_depth:
        :param safe_height:
        :param start_depth:
        :param step_down:
        :return:
        """
        op = EngraveOp(
            start_vertex=start_vertex,
            tool=tool,
            compound_data=shape_source_to_compound(shapes),
            clearance_height=clearance_height,
            final_depth=final_depth,
            safe_height=safe_height,
            start_depth=start_depth,
            step_down=step_down,
            coolant=coolant,
        )
        return self._add_op(op)

    def vcarve(
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
        coolant: Literal["None", "Flood", "Mist"] = "None",
    ):
        """
        V-Carve based on voronoi diagrams.

        Verify the tool path carefully! This algorithm is sometimes
        unstable.

        See https://wiki.freecad.org/Path_Vcarve for usage notes.

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
            coolant=coolant,
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
        coolant: Literal["None", "Flood", "Mist"] = "None",
    ):
        """
        3D surface op that mills the part using a XY scan pattern
        and a drop-down algorithm.

        If no shape(s) are provided, performs the OP on the whole model.

        See https://wiki.freecad.org/Path_Surface for usage notes.

        :param shapes:
        :param tool:
        :param bound_box:
        :param cut_mode:
        :param cut_pattern:
        :param cut_pattern_angle:
        :param cut_pattern_reversed:
        :param depth_offset:
        :param layer_mode:
        :param profile_edges:
        :param sample_interval:
        :param step_over:
        :param angular_deflection:
        :param linear_deflection:
        :param circular_use_g2g3:
        :param gap_threshold:
        :param optimize_linear_paths:
        :param optimize_step_over_transitions:
        :param avoid_last_x_faces:
        :param avoid_last_x_internal_features:
        :param boundary_adjustment:
        :param boundary_enforcement:
        :param multiple_features:
        :param internal_features_adjustment:
        :param internal_features_cut:
        :param start_point:
        :param scan_type:
        :param clearance_height:
        :param final_depth:
        :param safe_height:
        :param start_depth:
        :param step_down:
        :return:
        """
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
            coolant=coolant,
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
        coolant: Literal["None", "Flood", "Mist"] = "None",
    ):
        """
        Similar to the Surface OP, but performs the operation using a push
        cutter in the XY plane. Used for milling features on the XY-plane.

        If no shape(s) are provided, performs the OP on the whole model.

        See https://wiki.freecad.org/Path_Waterline for usage notes.

        :param shapes:
        :param tool:
        :param algorithm:
        :param bound_box:
        :param cut_mode:
        :param depth_offset:
        :param layer_mode:
        :param sample_interval:
        :param angular_deflection:
        :param linear_deflection:
        :param clearance_height:
        :param final_depth:
        :param safe_height:
        :param start_depth:
        :param step_down:
        :return:
        """
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
            coolant=coolant,
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
        coolant: Literal["None", "Flood", "Mist"] = "None",
    ):
        """
        Adaptive op generates a tool path to maintain constant cutter
        engagement.

        See https://wiki.freecad.org/Path_Adaptive for usage notes.

        :param shapes:
        :param tool:
        :param finishing_profile:
        :param force_inside_cut:
        :param helix_angle:
        :param helix_cone_angle:
        :param helix_diameter_limit:
        :param keep_tool_down_ratio:
        :param lift_distance:
        :param operation_type:
        :param side:
        :param step_over:
        :param stock_to_leave:
        :param tolerance:
        :param use_helix_arcs:
        :param use_outline:
        :param clearance_height:
        :param final_depth:
        :param safe_height:
        :param start_depth:
        :param step_down:
        :return:
        """
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
            coolant=coolant,
        )
        return self._add_op(op)


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
        """
        Dogbone dressup generates "dogbones" to tight corners that the
        cylindrical cutter would normally not be able to reach.

        See https://wiki.freecad.org/Path_DressupDogbone for usage notes.
        :param incision:
        :param custom:
        :param side:
        :param style:
        """
        self.params = map_params(
            self.mapping, incision=incision, custom=custom, side=side, style=style
        )

    def create(self, job_impl: "JobImpl", base):
        # DogboneII has this required code that exists only on the GUI side
        fc_obj = super().create(job_impl, base)
        job_impl.fc_job.Proxy.addOperation(fc_obj, base)

        # Also..
        # FreeCAD BUG: Need to do some manual black magic
        # Code copied from FreeCAD GUI side
        for i in fc_obj.Base.InList:
            if hasattr(i, "Group") and fc_obj.Base.Name in [o.Name for o in i.Group]:
                i.Group = [o for o in i.Group if o.Name != fc_obj.Base.Name]

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
        """
        Tab dressup generates tabs (or tags), useful for example when
        profiling to keep the part attached to the stock.

        See https://wiki.freecad.org/Path_DressupTag for usage notes.

        :param angle:
        :param height:
        :param width:
        :param positions:
        :param disabled:
        :param fillet_radius:
        :param segmentation_factor:
        """
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

    def create(self, job_impl: "JobImpl", base):
        obj = super().create(job_impl, base)

        # FreeCAD BUG: Need to do some manual black magic
        # Code copied from FreeCAD GUI side
        for i in obj.Base.InList:
            if hasattr(i, "Group") and obj.Base.Name in [o.Name for o in i.Group]:
                i.Group = [o for o in i.Group if o.Name != obj.Base.Name]

        return obj


Stock = StockImpl
