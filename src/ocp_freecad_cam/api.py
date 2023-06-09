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
from typing import Literal

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
    extract_topods_shapes,
    shape_source_to_compound_brep,
    shape_to_brep,
    transform_shape,
)
from ocp_freecad_cam.common import FaceSource, Plane, PlaneSource
from ocp_freecad_cam.operations import FaceOp, Op, PocketOp, ProfileOp
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

        return visualize_fc_job(self.fc_job, reverse_transform_tsrf(self.top_plane))

    def to_gcode(self):
        if self._needs_build:
            self._build()

        job = self.job
        postlist = buildPostList(job)
        processor = PostProcessor.load(job.PostProcessor)

        self.doc.saveAs("test2.fcstd")
        print(postlist)

        for idx, section in enumerate(postlist):
            name, sublist = section
            with tempfile.NamedTemporaryFile() as tmp_file:
                gcode = processor.export(sublist, tmp_file.name, "--no-show-editor")
                return gcode

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
        *args,
        side: Literal["in", "out"] = "out",
        **kwargs,
    ):
        """
        2.5D profile operation will cut the
        :param faces:
        :param args:
        :param kwargs:
        :return:
        """
        self.set_active()
        side = ProfileOp.kwargs_mapping["side"][side]
        op = ProfileOp(
            self,
            *args,
            side=side,
            tool_controller=tool.tool_controller,
            **shape_source_to_compound_brep(shapes, self._forward_trsf),
            **kwargs,
        )
        self._add_op(op)
        return self

    def _profile(self, base):
        pass

    def face(
        self, shapes: ShapeSource, *args, tool: "Toolbit", finish_depth=0.0, **kwargs
    ) -> "Job":
        self.set_active()
        op = FaceOp(
            self,
            *args,
            tool_controller=tool.tool_controller,
            finish_depth=finish_depth,
            **shape_source_to_compound_brep(shapes, self._forward_trsf),
            **kwargs,
        )
        self._add_op(op)
        return self

    def pocket(
        self, shapes: ShapeSource, *args, tool: "Toolbit", finish_depth=0.0, **kwargs
    ) -> "Job":
        self.set_active()
        op = PocketOp(
            self,
            *args,
            tool_controller=tool.tool_controller,
            finish_depth=finish_depth,
            **shape_source_to_compound_brep(shapes, self._forward_trsf),
            **kwargs,
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

    @property
    def tool_controller(self):
        if self._tool_controller is None:
            self.create()
        return self._tool_controller

    def create(self):
        tool_shape = Bit.findToolShape(self.tool_file_name, self.path)
        if not tool_shape:
            raise ValueError(
                f"Could not find tool {self.tool_file_name} (path: {self.path})"
            )

        self.obj = Bit.Factory.Create(self.tool_name, tool_shape)
        self._tool_controller = Controller.Create(
            f"TC: {self.tool_name}", tool=self.obj, toolNumber=self.tool_number
        )

        for k, v in self.props.items():
            PathUtil.setProperty(self.obj, self.prop_mapping[k], v)

    def clean_props(self, **kwargs):
        return {k: v for k, v in kwargs.items() if v is not None}


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
        tool_name: str,
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

        self.props = self.clean_props(
            chip_load=chip_load,
            flutes=flutes,
            material=material,
            cutting_edge_height=cutting_edge_height,
            diameter=diameter,
            length=length,
            shank_diameter=shank_diameter,
        )


class Ballnose(Endmill):
    file_name = "ballnose.fcstd"
