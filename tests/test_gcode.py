import cadquery as cq

from ocp_freecad_cam import Endmill, Job


def test_cq_spindle_feeds_and_speeds():
    box = cq.Workplane().box(10, 10, 1)
    top = box.faces(">Z").workplane()
    profile_shape = box.faces("<Z")
    tool = Endmill(diameter=1, h_feed=250, v_feed=50, speed=12000)
    job = Job(top, box, "grbl").profile(profile_shape, tool)
    gcode = job.to_gcode()

    assert "F50" in gcode
    assert "F250" in gcode
    assert "S12000" in gcode
