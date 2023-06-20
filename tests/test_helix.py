import cadquery as cq

from ocp_freecad_cam import Endmill
from ocp_freecad_cam.api import Job


def test_drill():
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

    tool = Endmill(diameter="0.5 mm")
    job = Job(top, wp, "grbl")
    job = job.helix(hole_edges, tool)
    job.to_gcode()
    job.show()
