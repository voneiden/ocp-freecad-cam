import cadquery as cq

from ocp_freecad_cam import Endmill, Job


def test_shared_tool_between_jobs():
    """
    Test that the same Toolbit instance can be used across multiple jobs.

    Regression test for: without resetting _tool_controller in _build,
    having multiple builds with shared tools causes 'No Tool Controllers exist'.
    """
    model = cq.Workplane().box(50, 50, 10)
    top = model.faces(">Z").workplane()

    tool = Endmill(diameter="10 mm", cutting_edge_height="10 mm", length="30 mm")

    Job(top, model, "grbl").face(model, tool).to_gcode()
    Job(top, model, "grbl").face(model, tool).to_gcode()
