import io
import logging
import tempfile
from abc import ABC

import FreeCAD
import Part
import Path.Base.SetupSheet as PathSetupSheet
import Path.Log as Log
from OCP.BRepTools import BRepTools
from OCP.TopoDS import TopoDS_Builder, TopoDS_Compound, TopoDS_Face, TopoDS_Shape
from Path.Main import Job as FCJob
from Path.Op import MillFace, PocketShape
from Path.Post.Command import buildPostList
from Path.Post.Processor import PostProcessor

from ocp_freecad_cam.common import FaceSource, Plane, PlaneSource
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
        faces = extract_faces(faces)
        transformed_faces = [
            forward_transform(job.top_plane, cq.Face(face)).wrapped for face in faces
        ]
        self.op_breps = [to_brep(face) for face in transformed_faces]

    def fc_op(self):
        raise NotImplemented

    def execute(self, doc):
        op_features = []
        for i, brep in enumerate(self.op_breps):
            fc_compound = Part.Face()
            fc_compound.importBrepFromString(brep)
            feature = doc.addObject("Part::Feature", f"brep_{self.n}_{i}")
            feature.Shape = fc_compound
            op_features.append((feature, ("Face1",)))
        fc_op = self.fc_op()
        fc_op.Base = op_features
        fc_op.Proxy.execute(fc_op)


class PocketOp(AreaOp):
    """2.5D pocket op"""

    def fc_op(self):
        name = self.label
        PathSetupSheet.RegisterOperation(
            name, PocketShape.Create, PocketShape.SetupProperties
        )
        return PocketShape.Create(name)


class FaceOp(AreaOp):
    def fc_op(self):
        name = self.label
        PathSetupSheet.RegisterOperation(
            name, MillFace.Create, MillFace.SetupProperties
        )
        fc_op = MillFace.Create(name)
        fc_op.BoundaryShape = "Stock"
        return fc_op


class Job:
    def __init__(self, top_plane: PlaneSource, obj):
        self.top_plane = extract_plane(top_plane)
        transformed_obj = forward_transform(self.top_plane, obj)
        self.job_obj_brep = to_brep(transformed_obj.wrapped)  # todo quick hack
        self.ops: list[Op] = []
        self.fc_job = None

    def show(self):
        return visualize_fc_job(self.fc_job, reverse_transform_tsrf(self.top_plane))

    def to_gcode(self):
        doc = FreeCAD.newDocument()
        fc_compound = Part.Compound()
        fc_compound.importBrepFromString(self.job_obj_brep)
        feature = doc.addObject("Part::Feature", f"root_brep")
        feature.Shape = fc_compound

        job = FCJob.Create("Job", [feature])
        self.fc_job = job.Proxy
        job.PostProcessor = "grbl"
        job.Stock.ExtZpos = 0
        job.Stock.ExtZneg = 0
        job.Tools.Group[0].Tool.Diameter = 1

        for op in self.ops:
            op.execute(doc)

        pp = job.PostProcessor

        print(dir(pp))
        doc.recompute()

        postlist = buildPostList(job)
        processor = PostProcessor.load(job.PostProcessor)

        doc.saveAs("test2.fcstd")
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


def create_job_transformations(top_plane):
    """
    Notes on transformation:

    FreeCAD will place the job zero into the bounding box's top plane's
    center.

    Only thing that matters when sending BREP's to FreeCAD is the orientation
    """


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


def reverse_transform(plane: Plane, shape):
    if cq and isinstance(plane, cq.Plane):
        return shape.transformShape(plane.rG)

    elif b3d and isinstance(plane, b3d.Plane):
        return plane.from_local_coords(shape)

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
