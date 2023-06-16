"""
This is the user facing API of ocp_freecad_cam
"""
import io
import logging
import tempfile
from typing import Literal, Optional

import FreeCAD
import Part
import Path.Log as Log
import PathScripts.PathUtils as PathUtils
from OCP.BRepTools import BRepTools
from OCP.TopoDS import TopoDS_Builder, TopoDS_Compound, TopoDS_Face, TopoDS_Shape
from Path.Dressup import DogboneII, Tags
from Path.Main import Job as FCJob
from Path.Post.Command import buildPostList
from Path.Post.Processor import PostProcessor
from Path.Tool import Bit, Controller

from ocp_freecad_cam.api_util import (
    AutoUnitKey,
    CompoundSource,
    ShapeSource,
    apply_params,
    extract_topods_shapes,
    map_params,
    scale_shape,
    shape_source_to_compound_brep,
    shape_to_brep,
    transform_shape,
)
from ocp_freecad_cam.common import FaceSource, Plane, PlaneSource
from ocp_freecad_cam.operations import (
    DeburrOp,
    Dressup,
    DrillOp,
    FaceOp,
    HelixOp,
    Op,
    PocketOp,
    ProfileOp,
    Surface3DOp,
    VCarveOp,
)
from ocp_freecad_cam.visualizer import visualize_fc_job

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
        postprocessor: Literal[
            "KineticNCBeamicon2",
            "centroid",
            "comparams",
            "dxf",
            "dynapath",
            "fablin",
            "fangling",
            "fanuc",
            "grbl",
            "heidenhain",
            "jtech",
            "linuxcnc",
            "mach3_mach4",
            "marlin",
            "nccad",
            "opensbp",
            "philips",
            "refactored_centroid",
            "refactored_grbl",
            "refactored_linuxcnc",
            "refactored_mach3_mach4",
            "refactored_test",
            "rml",
            "rrf",
            "smoothie",
            "uccnc",
        ] = None,
        units: Literal["metric", "imperial"] = "metric",
        geometry_tolerance=None,
    ):
        self.top_plane = extract_plane(top_plane)

        # Internal attributes
        self.ops: list[Op] = []
        self.fc_job = None
        self._needs_build = True
        self.doc = None
        self.postprocessor = postprocessor
        self.units = units

        # FreeCAD attributes
        self.geometry_tolerance = geometry_tolerance

        # Prepare job model
        model_compounds = extract_topods_shapes(model, compound=True)
        if (model_count := len(model_compounds)) != 1:
            raise ValueError(
                f"Job should be based around a single compound (got {model_count})"
            )
        transformed_job_model = transform_shape(model_compounds[0], self._forward_trsf)
        if sf := self._scale_factor:
            transformed_job_model = scale_shape(transformed_job_model, sf)

        self.job_obj_brep = shape_to_brep(transformed_job_model)

    @property
    def _scale_factor(self):
        if self.units == "metric":
            return None
        elif self.units == "imperial":
            return 25.4
        raise ValueError(f"Unknown unit: ({self.units})")

    def _build(self):
        if self.doc:
            FreeCAD.closeDocument(self.doc)

        self.doc = FreeCAD.newDocument("ocp_freecad_cam")
        self.set_active()
        fc_compound = Part.Compound()
        fc_compound.importBrepFromString(self.job_obj_brep)
        feature = self.doc.addObject("Part::Feature", f"root_brep")
        feature.Shape = fc_compound

        job = FCJob.Create("Job", [feature])
        self.job = job
        self.fc_job = job.Proxy

        # Remove default tools as we'll create our own later
        # Necessary also because of  buggy FX implementation
        tools = [tool for tool in self.job.Tools.Group]
        for tool in tools:
            self.job.Tools.removeObject(tool)
        if self.postprocessor:
            job.PostProcessor = self.postprocessor
        job.Stock.ExtZpos = 0
        job.Stock.ExtZneg = 0

        for op in self.ops:
            op.execute(self.doc)

        self.doc.recompute()
        self._needs_build = False

    def show(self):
        if self._needs_build:
            self._build()

        return visualize_fc_job(self.job, reverse_transform_tsrf(self.top_plane))

    def to_gcode(self):
        if self.postprocessor is None:
            raise ValueError(
                "No postprocessor set - set Job postprocessor to a valid value"
            )
        if self._needs_build:
            self._build()

        job = self.job
        postlist = buildPostList(job)
        processor = PostProcessor.load(job.PostProcessor)

        for idx, section in enumerate(postlist):
            name, sublist = section
            with tempfile.NamedTemporaryFile() as tmp_file:
                options = ["--no-show-editor"]
                if self.units == "imperial":
                    options.append("--inches")

                gcode = processor.export(sublist, tmp_file.name, " ".join(options))
                return gcode

    def save_fcstd(self, filename="debug.fcstd"):
        if self._needs_build:
            self._build()

        self.doc.saveAs(filename)

    def _add_op(self, op: Op):
        self._needs_build = True
        self.ops.append(op)

    def set_active(self):
        FreeCAD.setActiveDocument(self.doc.Name)

    @property
    def _forward_trsf(self):
        return forward_transform_tsrf(self.top_plane)

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
            self,
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
            **shape_source_to_compound_brep(
                shapes, self._forward_trsf, self._scale_factor
            ),
        )
        self._add_op(op)
        return self

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
        **kwargs,
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
            self,
            finish_depth=finish_depth,
            boundary=boundary,
            clear_edges=clear_edges,
            exclude_raised=exclude_raised,
            pattern=pattern,
            tool=tool,
            **shape_source_to_compound_brep(
                shapes, self._forward_trsf, self._scale_factor
            ),
            **kwargs,
        )
        self._add_op(op)
        return self

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
            self,
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
            **shape_source_to_compound_brep(
                shapes, self._forward_trsf, self._scale_factor
            ),
        )
        self._add_op(op)
        return self

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
        **kwargs,
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
        :param kwargs:
        :return:
        """

        op = DrillOp(
            self,
            tool=tool,
            dwell_time=dwell_time,
            extra_offset=extra_offset,
            peck_depth=peck_depth,
            keep_tool_down=keep_tool_down,
            retract_height=retract_height,
            chip_break_enabled=chip_break_enabled,
            **shape_source_to_compound_brep(
                shapes, self._forward_trsf, self._scale_factor
            ),
            **kwargs,
        )
        self._add_op(op)
        return self

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
        **kwargs,
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
        :param kwargs:
        :return:
        """

        op = HelixOp(
            self,
            direction=direction,
            offset_extra=offset_extra,
            start_radius=start_radius,
            start_side=start_side,
            step_over=step_over,
            # Op
            tool=tool,
            **shape_source_to_compound_brep(
                shapes, self._forward_trsf, self._scale_factor
            ),
            **kwargs,
        )
        self._add_op(op)
        return self

    def deburr(
        self,
        shapes: ShapeSource,
        tool: "Toolbit",
        *,
        width: float | str = "1 mm",
        extra_depth: float | str = "0.5 mm",
        direction: Literal["cw", "ccw"] = "cw",
        entry_point: int = 0,
    ):
        op = DeburrOp(
            self,
            width=width,
            extra_depth=extra_depth,
            direction=direction,
            entry_point=entry_point,
            # Op
            tool=tool,
            **shape_source_to_compound_brep(
                shapes, self._forward_trsf, self._scale_factor
            ),
        )
        self._add_op(op)
        return self

    def v_carve(
        self,
        shapes: ShapeSource,
        tool: "Toolbit",
        *,
        discretize: float = 0.01,
        colinear: float = 10.0,
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
            self,
            discretize=discretize,
            colinear=colinear,
            # Op
            tool=tool,
            **shape_source_to_compound_brep(
                shapes, self._forward_trsf, self._scale_factor
            ),
        )
        self._add_op(op)
        return self

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
    ):
        op = Surface3DOp(
            self,
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
            **shape_source_to_compound_brep(
                shapes, self._forward_trsf, self._scale_factor, allow_none=True
            ),
        )
        self._add_op(op)
        return self


def extract_plane(plane_source: PlaneSource) -> Plane:
    if cq:
        # ace.transformShape(job.top.fG)
        if isinstance(plane_source, cq.Workplane):
            return plane_source.plane

        elif isinstance(plane_source, cq.Plane):
            return plane_source

        elif isinstance(plane_source, cq.Face):
            gp_pln = plane_source.toPln()
            ax3 = gp_pln.Position()
            origin = cq.Vector(ax3.Location())
            x_dir = cq.Vector(ax3.XDirection())
            normal = cq.Vector(ax3.Direction())
            return cq.Plane(origin, x_dir, normal)

    if b3d:
        if isinstance(plane_source, b3d.Plane):
            return plane_source
        elif isinstance(plane_source, b3d.Face):
            return b3d.Plane(face=plane_source)

    raise ValueError(f"Unknown type of plane: {type(plane_source)}")


def forward_transform(plane: Plane, shape: TopoDS_Shape) -> TopoDS_Shape:
    if cq and isinstance(plane, cq.Plane):
        return cq.Shape(shape).transformShape(plane.fG).wrapped

    elif b3d and isinstance(plane, b3d.Plane):
        return plane.to_local_coords(b3d.Shape(shape)).wrapped

    raise ValueError(f"Unknown type of plane: {type(plane)}")


def reverse_transform(plane: Plane, shape: TopoDS_Shape) -> TopoDS_Shape:
    if cq and isinstance(plane, cq.Plane):
        return cq.Shape(shape).transformShape(plane.rG).wrapped

    elif b3d and isinstance(plane, b3d.Plane):
        return plane.from_local_coords(b3d.Shape(shape).wrapped)

    raise ValueError(f"Unknown type of plane: {type(plane)}")


def forward_transform_tsrf(plane: Plane):
    if cq and isinstance(plane, cq.Plane):
        return plane.fG.wrapped.Trsf()

    elif b3d and isinstance(plane, b3d.Plane):
        return plane.forward_transform.wrapped.Trsf()

    raise ValueError(f"Unknown type of plane: {type(plane)}")


def reverse_transform_tsrf(plane: Plane):
    if cq and isinstance(plane, cq.Plane):
        return plane.rG.wrapped.Trsf()

    elif b3d and isinstance(plane, b3d.Plane):
        return plane.reverse_transform.wrapped.Trsf()

    raise ValueError(f"Unknown type of plane: {type(plane)}")


def extract_faces(face_source: FaceSource) -> list[TopoDS_Face]:
    if isinstance(face_source, list):
        faces = []
        for element in face_source:
            faces += extract_faces(element)
        return faces

    if cq:
        if isinstance(face_source, cq.Workplane):
            return [f.wrapped for f in face_source.objects if isinstance(f, cq.Face)]
        elif isinstance(face_source, cq.Face):
            return [face_source.wrapped]
    if b3d:
        if isinstance(face_source, b3d.Face):
            return [face_source.wrapped]

    raise ValueError(f"Unknown type of face: {type(face_source)}")


def shapes_to_compound(shapes: list[TopoDS_Shape]) -> TopoDS_Compound:
    comp = TopoDS_Compound()
    comp_builder = TopoDS_Builder()
    comp_builder.MakeCompound(comp)

    for s in shapes:
        comp_builder.Add(comp, s)

    return comp


def to_brep(shape: TopoDS_Shape):
    data = io.BytesIO()
    BRepTools.Write_s(shape, data)
    data.seek(0)
    return data.read().decode("utf8")


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


class Bullnose(Endmill):
    pass


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
