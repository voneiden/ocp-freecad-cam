import cadquery as cq
import pytest

from ocp_freecad_cam import Endmill
from ocp_freecad_cam.api import Job


@pytest.mark.parametrize(
    "test_unit,expected_gcode_1,expected_gcode_2",
    [
        ("metric", "G21\n", "G1 X-5.000 Y-5.500 Z-1.000\n"),
        ("imperial", "G20\n", "G1 X-5.0000 Y-5.5000 Z-1.0000\n"),
    ],
)
def test_cq_profile(test_unit, expected_gcode_1, expected_gcode_2):
    box = cq.Workplane().box(10, 10, 1)
    top = box.faces(">Z").workplane()
    profile_shape = box.faces("<Z")
    tool = Endmill(diameter=1)
    job = Job(top, box, "grbl", units=test_unit)
    job = job.profile(profile_shape, tool)
    gcode = job.to_gcode()

    assert expected_gcode_1 in gcode
    assert expected_gcode_2 in gcode
