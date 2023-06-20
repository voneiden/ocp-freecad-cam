import cadquery as cq

from ocp_freecad_cam import Drill, Job

wp = (
    cq.Workplane()
    .box(5, 5, 2)
    .faces(">Z")
    .workplane()
    .pushPoints([(-1.5, -1.5), (0, 1.5), (0.5, -1)])
    .circle(0.5)
    .cutThruAll()
)

top = wp.faces(">Z").workplane()
hole_edges = wp.faces("<Z").objects[0].innerWires()


tool = Drill(diameter="1 mm")
job = Job(top, wp).drill(hole_edges, tool)
