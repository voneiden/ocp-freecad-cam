import cadquery as cq

from ocp_freecad_cam import Endmill
from ocp_freecad_cam.api import Dogbone, Job, Tab


def test_cq_tab():
    box = cq.Workplane().box(10, 10, 2)
    top = box.faces(">Z").workplane()
    tool = Endmill(diameter=1)
    job = Job(top, box, "grbl").profile(box.faces("<Z"), tool, dressups=[Tab()])
    gcode = job.to_gcode()
    assert "DressupTag" in gcode
    assert "ProfileOp_1" not in gcode


def test_cq_dogbone():
    box = cq.Workplane().box(10, 10, 2)
    top = box.faces(">Z").workplane()
    tool = Endmill(diameter=1)
    job = Job(top, box, "grbl").pocket(box.faces(">Z"), tool, dressups=[Dogbone()])
    gcode = job.to_gcode()
    assert "(Begin operation: DressupDogbone)" in gcode
    assert "(Begin operation: PocketOp_1)" not in gcode
