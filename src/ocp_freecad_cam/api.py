"""
This is the user facing API of ocp_freecad_cam

TODO: Investigate setting FreeCAD units
* Root.BaseApp.Preferences.Units
  * UserSchema
    * "6" for Metric CNC
    * "3" for Imperial Decimal
    * "5" for US Building
TODO: Investigate setting opencamlib settings
* Root.BaseApp.Preferences.Path.EnableAdvancedOCLFeatures "1"
TODO: Investigate setting absolute paths for toolbits?
* Root.BaseApp.Preferences.Path.UseAbsoluteToolPaths "1"

"""
import io
import logging
import tempfile
from typing import Literal, Optional

import FreeCAD
import Part
import Path.Base.Util as PathUtil
import Path.Log as Log
from OCP.BRepTools import BRepTools
from OCP.TopoDS import TopoDS_Builder, TopoDS_Compound, TopoDS_Face, TopoDS_Shape
from Path.Main import Job as FCJob
from Path.Post.Command import buildPostList
from Path.Post.Processor import PostProcessor
from Path.Tool import Bit, Controller

from ocp_freecad_cam.api_util import (
    CompoundSource,
    ShapeSource,
    clean_props,
    extract_topods_shapes,
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
        units: Literal["metric", "imperial"] = "metric",
        geometry_tolerance=None,
    ):
        self.top_plane = extract_plane(top_plane)

        # Prepare job model
        model_compounds = extract_topods_shapes(model, compound=True)
        if model_count := len(model_compounds) != 1:
            raise ValueError(
                f"Job should be based around a single compound (got {model_count})"
            )
        self.job_obj_brep = shape_to_brep(
            transform_shape(model_compounds[0], self._forward_trsf)
        )

        # Internal attributes
        self.ops: list[Op] = []
        self.fc_job = None
        self._needs_build = True
        self.units = units

        # FreeCAD attributes
        self.geometry_tolerance = geometry_tolerance

        # Prep document
        self._configure_freecad()
        self.doc = FreeCAD.newDocument()

    def _configure_freecad(self):
        # Configure units
        param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Units")
        if self.units == "metric":
            param.SetInt("UserSchema", 6)
        elif self.units == "imperial":
            param.SetInt("UserSchema", 3)
        else:
            raise ValueError(f"Unknown unit: {self.units}")

        # Enable OCL
        param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Path")
        param.SetInt("EnableAdvancedOCLFeatures", 1)

        # Absolute toolpaths (not sure if needed?)
        # param.SetInt("UseAbsoluteToolPaths", 1)

    def _build(self):
        fc_compound = Part.Compound()
        fc_compound.importBrepFromString(self.job_obj_brep)
        feature = self.doc.addObject("Part::Feature", f"root_brep")
        feature.Shape = fc_compound

        job = FCJob.Create("Job", [feature])
        self.job = job
        self.fc_job = job.Proxy
        job.PostProcessor = "grbl"
        job.Stock.ExtZpos = 0
        job.Stock.ExtZneg = 0
        job.Tools.Group[0].Tool.Diameter = 1

        for op in self.ops:
            op.execute(self.doc)

        self.doc.recompute()
        self._needs_build = False

    def show(self):
        if self._needs_build:
            self._build()

        return visualize_fc_job(self.job, reverse_transform_tsrf(self.top_plane))

    def to_gcode(self):
        if self._needs_build:
            self._build()

        job = self.job
        postlist = buildPostList(job)
        processor = PostProcessor.load(job.PostProcessor)

        print(postlist)

        for idx, section in enumerate(postlist):
            print("idx", id)

            name, sublist = section
            print("-name", name)
            print("-sublist", sublist)
            print([s.Name for s in sublist])
            print(sublist[0].Path.Commands)

            with tempfile.NamedTemporaryFile() as tmp_file:
                gcode = processor.export(sublist, tmp_file.name, "--no-show-editor")
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

        self.set_active()
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
            **shape_source_to_compound_brep(shapes, self._forward_trsf),
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
        self.set_active()
        op = FaceOp(
            self,
            finish_depth=finish_depth,
            boundary=boundary,
            clear_edges=clear_edges,
            exclude_raised=exclude_raised,
            pattern=pattern,
            tool=tool,
            **shape_source_to_compound_brep(shapes, self._forward_trsf),
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
        self.set_active()
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
            **shape_source_to_compound_brep(shapes, self._forward_trsf),
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
        self.set_active()
        op = DrillOp(
            self,
            tool=tool,
            dwell_time=dwell_time,
            extra_offset=extra_offset,
            peck_depth=peck_depth,
            keep_tool_down=keep_tool_down,
            retract_height=retract_height,
            chip_break_enabled=chip_break_enabled,
            **shape_source_to_compound_brep(shapes, self._forward_trsf),
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
        self.set_active()
        op = HelixOp(
            self,
            direction=direction,
            offset_extra=offset_extra,
            start_radius=start_radius,
            start_side=start_side,
            step_over=step_over,
            # Op
            tool=tool,
            **shape_source_to_compound_brep(shapes, self._forward_trsf),
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
        self.set_active()
        op = DeburrOp(
            self,
            width=width,
            extra_depth=extra_depth,
            direction=direction,
            entry_point=entry_point,
            # Op
            tool=tool,
            **shape_source_to_compound_brep(shapes, self._forward_trsf),
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
        V-Carve based on voronoi diagrams
        :param shapes:
        :param tool:
        :param discretize: Try a smaller value if getting too many retracts.
        :param colinear:
        :return:
        """
        self.set_active()
        op = VCarveOp(
            self,
            discretize=discretize,
            colinear=colinear,
            # Op
            tool=tool,
            **shape_source_to_compound_brep(shapes, self._forward_trsf),
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
    prop_mapping = {}

    def __init__(self, tool_name: str, tool_file_name: str, tool_number=1, path=None):
        self.tool_name = tool_name
        self.tool_file_name = tool_file_name
        self.tool_number = tool_number
        self.path = path
        self.props = {}
        self.obj = None
        self._tool_controller = None

    def tool_controller(self, job):
        if self._tool_controller is None:
            self.create(job)
        return self._tool_controller

    def create(self, job):
        tool_shape = Bit.findToolShape(self.tool_file_name, self.path)
        if not tool_shape:
            raise ValueError(
                f"Could not find tool {self.tool_file_name} (path: {self.path})"
            )

        self.obj = Bit.Factory.Create(self.tool_name, tool_shape)
        self._tool_controller = Controller.Create(
            f"TC: {self.tool_name}", tool=self.obj, toolNumber=self.tool_number
        )

        job.addToolController(self._tool_controller)

        for k, v in self.props.items():
            PathUtil.setProperty(self.obj, self.prop_mapping[k], v)


class Endmill(Toolbit):
    file_name = "endmill.fcstd"
    prop_mapping = {
        "chip_load": "ChipLoad",
        "flutes": "Flutes",
        "material": "Material",
        "spindle_direction": "SpindleDirection",
        "cutting_edge_height": "CuttingEdgeHeight",
        "diameter": "Diameter",
        "length": "Length",
        "shank_diameter": "Shank Diameter",
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
        super().__init__(tool_name, self.file_name, tool_number=tool_number)

        self.props = clean_props(
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
    file_name = "ballnose.fcstd"


class VBit(Endmill):
    file_name = "v-bit.fcstd"

    prop_mapping = {
        **Endmill.prop_mapping,
        "tip_angle": "CuttingEdgeAngle",
        "tip_diameter": "TipDiameter",
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
        super().__init__(tool_name, self.file_name, tool_number=tool_number)
        self.props = clean_props(
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


class Bullnose(Endmill):
    pass
