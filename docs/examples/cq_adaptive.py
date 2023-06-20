import cadquery as cq

from ocp_freecad_cam import Endmill, Job
from ocp_freecad_cam.api_util import Expression

wp = (
    cq.Workplane()
    .rect(10, 10)
    .extrude(5)
    .faces(">Z")
    .workplane()
    .rect(8, 8)
    .cutBlind(-1)
    .faces(">Z")
    .rect(10, 2)
    .cutBlind(-1)
)

pocket = wp.faces(">Z[1]")
top = wp.faces(">Z").workplane()
tool = Endmill(diameter=1)
job = Job(top, wp).adaptive(
    pocket,
    tool=tool,
    step_over=50,
    start_depth=Expression("0 mm"),
)
