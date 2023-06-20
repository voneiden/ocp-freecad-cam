import cadquery as cq

from ocp_freecad_cam import Endmill
from ocp_freecad_cam.api import Job


def test_cq_adaptive():
    box = cq.Workplane().box(10, 10, 1)
    top = box.faces(">Z").workplane()
    adaptive_shape = box.faces(">Z")
    tool = Endmill(diameter=1, v_feed=150)
    job = Job(top, box, "grbl", units="metric")
    job = job.adaptive(adaptive_shape, tool)
    gcode = job.to_gcode()
    lines = gcode.split("\n")
    start_index = lines.index("(Begin operation: AdaptiveOp_1)")
    finish_index = lines.index("(Finish operation: AdaptiveOp_1)")
    job.show()  # coverage for visualizer
    job.save_fcstd("debug.fcstd")
    # Don't care what it generates as long as it's at least 100 lines
    assert (finish_index - start_index) > 100
    assert "F150" in gcode
