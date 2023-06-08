import io
import logging
import tempfile

import FreeCAD
import Part
import Path.Log as Log
from OCP.BRepTools import BRepTools
from OCP.TopoDS import TopoDS_Builder, TopoDS_Compound, TopoDS_Face, TopoDS_Shape
from Path.Main import Job as FCJob
from Path.Post.Command import buildPostList
from Path.Post.Processor import PostProcessor

from ocp_freecad_cam.common import FaceSource, Plane, PlaneSource
from ocp_freecad_cam.operations import FaceOp, Op, PocketOp
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
    def __init__(self, top_plane: PlaneSource, obj):
        self.top_plane = extract_plane(top_plane)
        transformed_obj = forward_transform(self.top_plane, obj)
        self.job_obj_brep = to_brep(transformed_obj.wrapped)  # todo quick hack
        self.ops: list[Op] = []
        self.fc_job = None
        self.needs_build = True
        self.doc = None

    def _build(self):
        self.doc = FreeCAD.newDocument()
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

    def show(self):
        if self.needs_build:
            self._build()

        return visualize_fc_job(self.fc_job, reverse_transform_tsrf(self.top_plane))

    def to_gcode(self):
        if self.needs_build:
            self._build()

        job = self.job
        postlist = buildPostList(job)
        processor = PostProcessor.load(job.PostProcessor)

        self.doc.saveAs("test2.fcstd")
        print(postlist)

        for idx, section in enumerate(postlist):
            name, sublist = section
            with tempfile.NamedTemporaryFile() as tmp:
                gcode = processor.export(sublist, tmp.name, "--no-show-editor")
                print("Got gcode", gcode)

    def _add_op(self, op: Op):
        self.needs_build = True
        self.ops.append(op)

    def pocket(self, faces: FaceSource, *args, **kwargs) -> "Job":
        breps = faces_to_transformed_breps(faces, self.top_plane)
        op = PocketOp(self, breps, *args, **kwargs)
        self._add_op(op)
        return self

    def face(self, faces: FaceSource, *args, **kwargs) -> "Job":
        breps = faces_to_transformed_breps(faces, self.top_plane)
        op = FaceOp(self, breps, *args, **kwargs)
        self._add_op(op)
        return self


def faces_to_transformed_breps(faces: FaceSource, top_plane: Plane):
    faces = extract_faces(faces)
    transformed_faces = [
        forward_transform(top_plane, cq.Face(face)).wrapped for face in faces
    ]
    return [to_brep(face) for face in transformed_faces]


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
