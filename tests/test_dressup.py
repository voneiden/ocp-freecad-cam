import platform

import cadquery as cq
import pytest
from freezegun import freeze_time

from ocp_freecad_cam import Endmill
from ocp_freecad_cam.api import Dogbone, Job, Ramp, Tab


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


def perform_ramp_test():
    box = cq.Workplane().box(10, 10, 2)
    top = box.faces(">Z").workplane()
    tool = Endmill(diameter=1)
    job = Job(top, box, "grbl").profile(box.faces("<Z"), tool, dressups=[Ramp()])
    gcode = job.to_gcode()
    return gcode


@freeze_time("2025-12-14")
@pytest.mark.skipif(
    platform.system() == "Windows", reason="Test is not compatible with Windows"
)
def test_cq_ramp_non_windows():
    gcode = perform_ramp_test()
    expected_gcode = "(Exported by FreeCAD)\n(Post Processor: grbl_post)\n(Output Time:2025-12-14 00:00:00)\n(Begin preamble)\nG17 G90\nG21\n(Begin operation: Fixture)\n(Path: Fixture)\nG54\n(Finish operation: Fixture)\n(Begin operation: TC: )\n(Path: TC: )\n(TC: )\n(Begin toolchange)\n( M6 T1 )\n(Finish operation: TC: )\n(Begin operation: Ramp)\n(Path: Ramp)\nG0 X0.000 Y0.000 Z6.000\nG0 X5.354 Y5.354 Z6.000\nG0 X5.354 Y5.354 Z4.000\nG1 X5.462 Y5.191 Z3.887\nG1 X5.500 Y5.000 Z3.773\nG1 X5.500 Y-1.536 Z0.000\nG1 X5.500 Y5.000 Z0.000\nG3 X5.354 Y5.354 Z0.000 I-0.500 J-0.000 K0.000\nG2 X5.500 Y5.000 Z0.000 I-0.354 J-0.354 K0.000\nG1 X5.500 Y-5.000 Z0.000\nG2 X5.000 Y-5.500 Z0.000 I-0.500 J-0.000 K0.000\nG1 X-5.000 Y-5.500 Z0.000\nG2 X-5.500 Y-5.000 Z0.000 I-0.000 J0.500 K0.000\nG1 X-5.500 Y5.000 Z0.000\nG2 X-5.000 Y5.500 Z0.000 I0.500 J0.000 K0.000\nG1 X5.000 Y5.500 Z0.000\nG2 X5.354 Y5.354 Z0.000 I0.000 J-0.500 K0.000\nG1 X5.462 Y5.191 Z-0.113\nG1 X5.500 Y5.000 Z-0.227\nG1 X5.500 Y3.661 Z-1.000\nG1 X5.500 Y5.000 Z-1.000\nG3 X5.354 Y5.354 Z-1.000 I-0.500 J-0.000 K0.000\nG2 X5.500 Y5.000 Z-1.000 I-0.354 J-0.354 K0.000\nG1 X5.500 Y-5.000 Z-1.000\nG2 X5.000 Y-5.500 Z-1.000 I-0.500 J-0.000 K0.000\nG1 X-5.000 Y-5.500 Z-1.000\nG2 X-5.500 Y-5.000 Z-1.000 I-0.000 J0.500 K0.000\nG1 X-5.500 Y5.000 Z-1.000\nG2 X-5.000 Y5.500 Z-1.000 I0.500 J0.000 K0.000\nG1 X5.000 Y5.500 Z-1.000\nG2 X5.354 Y5.354 Z-1.000 I0.000 J-0.500 K0.000\nG1 X5.462 Y5.191 Z-1.113\nG1 X5.500 Y5.000 Z-1.227\nG1 X5.500 Y3.661 Z-2.000\nG1 X5.500 Y5.000 Z-2.000\nG3 X5.354 Y5.354 Z-2.000 I-0.500 J-0.000 K0.000\nG2 X5.500 Y5.000 Z-2.000 I-0.354 J-0.354 K0.000\nG1 X5.500 Y-5.000 Z-2.000\nG2 X5.000 Y-5.500 Z-2.000 I-0.500 J-0.000 K0.000\nG1 X-5.000 Y-5.500 Z-2.000\nG2 X-5.500 Y-5.000 Z-2.000 I-0.000 J0.500 K0.000\nG1 X-5.500 Y5.000 Z-2.000\nG2 X-5.000 Y5.500 Z-2.000 I0.500 J0.000 K0.000\nG1 X5.000 Y5.500 Z-2.000\nG2 X5.354 Y5.354 Z-2.000 I0.000 J-0.500 K0.000\nG0 X5.354 Y5.354 Z6.000\n(Finish operation: Ramp)\n(Begin postamble)\nM5\nG17 G90\nM2\n"  # noqa: E501
    assert gcode == expected_gcode


@freeze_time("2025-12-14")
@pytest.mark.skipif(
    platform.system() != "Windows", reason="Test is not compatible with Non-Windows"
)
def test_cq_ramp_on_windows():
    gcode = perform_ramp_test()
    expected_gcode = "(Exported by FreeCAD)\n(Post Processor: grbl_post)\n(Output Time:2025-12-14 00:00:00)\n(Begin preamble)\nG17 G90\nG21\n(Begin operation: Fixture)\n(Path: Fixture)\nG54\n(Finish operation: Fixture)\n(Begin operation: TC: )\n(Path: TC: )\n(TC: )\n(Begin toolchange)\n( M6 T1 )\n(Finish operation: TC: )\n(Begin operation: Ramp)\n(Path: Ramp)\nG0 X0.000 Y0.000 Z6.000\nG0 X5.354 Y5.354 Z6.000\nG0 X5.354 Y5.354 Z4.000\nG1 X5.462 Y5.191 Z3.887\nG1 X5.500 Y5.000 Z3.773\nG1 X5.500 Y-1.536 Z-0.000\nG1 X5.500 Y5.000 Z0.000\nG3 X5.354 Y5.354 Z0.000 I-0.500 J0.000 K0.000\nG2 X5.500 Y5.000 Z0.000 I-0.354 J-0.354 K0.000\nG1 X5.500 Y-5.000 Z0.000\nG2 X5.000 Y-5.500 Z0.000 I-0.500 J-0.000 K0.000\nG1 X-5.000 Y-5.500 Z0.000\nG2 X-5.500 Y-5.000 Z0.000 I-0.000 J0.500 K0.000\nG1 X-5.500 Y5.000 Z0.000\nG2 X-5.000 Y5.500 Z0.000 I0.500 J0.000 K0.000\nG1 X5.000 Y5.500 Z0.000\nG2 X5.354 Y5.354 Z0.000 I0.000 J-0.500 K0.000\nG1 X5.462 Y5.191 Z-0.113\nG1 X5.500 Y5.000 Z-0.227\nG1 X5.500 Y3.661 Z-1.000\nG1 X5.500 Y5.000 Z-1.000\nG3 X5.354 Y5.354 Z-1.000 I-0.500 J0.000 K0.000\nG2 X5.500 Y5.000 Z-1.000 I-0.354 J-0.354 K0.000\nG1 X5.500 Y-5.000 Z-1.000\nG2 X5.000 Y-5.500 Z-1.000 I-0.500 J-0.000 K0.000\nG1 X-5.000 Y-5.500 Z-1.000\nG2 X-5.500 Y-5.000 Z-1.000 I-0.000 J0.500 K0.000\nG1 X-5.500 Y5.000 Z-1.000\nG2 X-5.000 Y5.500 Z-1.000 I0.500 J0.000 K0.000\nG1 X5.000 Y5.500 Z-1.000\nG2 X5.354 Y5.354 Z-1.000 I0.000 J-0.500 K0.000\nG1 X5.462 Y5.191 Z-1.113\nG1 X5.500 Y5.000 Z-1.227\nG1 X5.500 Y3.661 Z-2.000\nG1 X5.500 Y5.000 Z-2.000\nG3 X5.354 Y5.354 Z-2.000 I-0.500 J0.000 K0.000\nG2 X5.500 Y5.000 Z-2.000 I-0.354 J-0.354 K0.000\nG1 X5.500 Y-5.000 Z-2.000\nG2 X5.000 Y-5.500 Z-2.000 I-0.500 J-0.000 K0.000\nG1 X-5.000 Y-5.500 Z-2.000\nG2 X-5.500 Y-5.000 Z-2.000 I-0.000 J0.500 K0.000\nG1 X-5.500 Y5.000 Z-2.000\nG2 X-5.000 Y5.500 Z-2.000 I0.500 J0.000 K0.000\nG1 X5.000 Y5.500 Z-2.000\nG2 X5.354 Y5.354 Z-2.000 I0.000 J-0.500 K0.000\nG0 X5.354 Y5.354 Z6.000\n(Finish operation: Ramp)\n(Begin postamble)\nM5\nG17 G90\nM2\n"  # noqa: E501
    assert gcode == expected_gcode
