import io
import sys
import tempfile
from abc import ABC
from typing import TypeAlias, Union

from OCP.BRepTools import BRepTools
from OCP.TopoDS import TopoDS_Builder, TopoDS_Compound, TopoDS_Face, TopoDS_Shape

FC_PATH = "/home/voneiden/Downloads/freecad/squashfs-root/usr/lib"
sys.path.append(FC_PATH)

MOD_PATH_PATH = "/home/voneiden/Downloads/freecad/squashfs-root/usr/Mod/Path"
sys.path.append(MOD_PATH_PATH)

FC_PYTHON = (
    "/home/voneiden/Downloads/freecad/squashfs-root/usr/lib/python3.10/site-packages/"
)
sys.path.append(FC_PYTHON)

# noinspection PyUnresolvedReferences
import FreeCAD

# noinspection PyUnresolvedReferences
import Part
import Path
from Path.Main import Job as FCJob
from Path.Op import MillFace, Pocket
from Path.Post.Command import buildPostList
from Path.Post.Processor import PostProcessor

try:
    import cadquery as cq
except ImportError:
    cq = None
try:
    import build123d as b3d
except ImportError:
    b3d = None

FaceSource: TypeAlias = Union[
    "cq.Workplane", "cq.Face", list["cq.Face"], "b3d.Face", list["b3d.Face"]
]
PlaneSource: TypeAlias = Union[
    "cq.Workplane", "cq.Plane", "cq.Face", "b3d.Plane", "b3d.Face"
]
Plane: TypeAlias = Union["cq.Plane", "b3d.Plane"]


class Op(ABC):
    def __init__(self, job: "Job", *args, name=None, **kwargs):
        self.job = job
        self.n = len(self.job.ops) + 1
        self.name = name

    def execute(self, doc):
        raise NotImplemented

    @property
    def label(self):
        if self.name:
            return self.name
        return f"{self.__class__.__name__}_{self.n}"


class AreaOp(Op, ABC):
    def __init__(self, job: "Job", faces: FaceSource, *args, **kwargs):
        super().__init__(job, *args, **kwargs)
        self.op_brep = to_brep(shapes_to_compound(extract_faces(faces)))

    def fc_op(self):
        raise NotImplemented

    def execute(self, doc):
        fc_compound = Part.Compound()
        fc_compound.importBrepFromString(self.op_brep)
        feature = doc.addObject("Part::Feature", f"brep_{self.n}")
        feature.Shape = fc_compound
        fc_op = self.fc_op()
        fc_op.Proxy.execute(fc_op)


class PocketOp(AreaOp):
    def fc_op(self):
        return Pocket.Create(self.label)


class FaceOp(AreaOp):
    def fc_op(self):
        fc_op = MillFace.Create(self.label)
        fc_op.BoundaryShape = "Stock"
        return fc_op


class Job:
    def __init__(self, top_plane: PlaneSource, obj):
        self.top_plane = extract_plane(top_plane)
        self.job_obj_brep = to_brep(obj.wrapped)  # todo quick hack
        self.ops: list[Op] = []

    def to_gcode(self):
        doc = FreeCAD.newDocument()
        fc_compound = Part.Compound()
        fc_compound.importBrepFromString(self.job_obj_brep)
        feature = doc.addObject("Part::Feature", f"root_brep")
        feature.Shape = fc_compound

        job = FCJob.Create("Job", [feature])
        job.PostProcessor = "grbl"
        job.Tools.Group[0].Tool.Diameter = 1

        for op in self.ops:
            op.execute(doc)

        pp = job.PostProcessor

        print(dir(pp))
        doc.recompute()

        postlist = buildPostList(job)
        processor = PostProcessor.load(job.PostProcessor)

        doc.saveAs("test.fcstd")
        print(postlist)

        for idx, section in enumerate(postlist):
            name, sublist = section
            with tempfile.NamedTemporaryFile() as tmp:
                gcode = processor.export(sublist, tmp.name, "--no-show-editor")
                print("Got gcode", gcode)

    def _add_op(self, op: Op):
        self.ops.append(op)

    def pocket(self, faces: FaceSource, *args, **kwargs) -> "Job":
        op = PocketOp(self, faces, *args, **kwargs)
        self._add_op(op)
        return self

    def face(self, faces: FaceSource, *args, **kwargs) -> "Job":
        op = FaceOp(self, faces, *args, **kwargs)
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


def forward_transform(plane: Plane, shape):
    if cq and isinstance(plane, cq.Plane):
        return shape.transformShape(plane.fG)

    elif b3d and isinstance(plane, b3d.Plane):
        return plane.to_local_coords(shape)

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
