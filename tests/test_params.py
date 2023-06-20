import io

import cadquery as cq
import FreeCAD
import Part
import pytest
from Path.Main import Job as FCJob

from ocp_freecad_cam import Endmill, VBit
from ocp_freecad_cam.api_util import AutoUnitKey
from ocp_freecad_cam.fc_impl import (
    DeburrOp,
    DrillOp,
    FaceOp,
    HelixOp,
    PocketOp,
    ProfileOp,
    Surface3DOp,
    VCarveOp,
)


@pytest.fixture
def fc_doc():
    doc = FreeCAD.newDocument("Test Doc")
    FreeCAD.setActiveDocument(doc.Name)
    yield doc
    FreeCAD.closeDocument(doc.Name)


@pytest.fixture
def fc_cube_base_feature(fc_doc):
    buffer = io.BytesIO()
    cmp = cq.Compound.makeCompound(cq.Workplane().box(5, 5, 5).objects)
    cmp.exportBrep(buffer)
    buffer.seek(0)
    brep = buffer.read().decode("utf8")
    fc_compound = Part.Compound()
    fc_compound.importBrepFromString(brep)
    feature = fc_doc.addObject("Part::Feature", f"root_brep")
    feature.Shape = fc_compound
    return feature


@pytest.fixture
def fc_job(fc_cube_base_feature):
    job = FCJob.Create("Job", [fc_cube_base_feature])
    tools = [tool for tool in job.Tools.Group]
    for tool in tools:
        job.Tools.removeObject(tool)

    return job


def endmill_tc(fc_job, unit):
    endmill = Endmill(diameter=1)
    return endmill.tool_controller(fc_job, unit)


def vbit_tc(fc_job, unit):
    vbit = VBit(tip_diameter=0.1, tip_angle=60)
    return vbit.tool_controller(fc_job, unit)


@pytest.mark.parametrize(
    "module,tc_f",
    [
        (ProfileOp, endmill_tc),
        (FaceOp, endmill_tc),
        (PocketOp, endmill_tc),
        (DrillOp, endmill_tc),
        (HelixOp, endmill_tc),
        (DeburrOp, endmill_tc),
        (VCarveOp, vbit_tc),
        (Surface3DOp, endmill_tc),
    ],
)
def test_params(fc_job, module, tc_f):
    tc = tc_f(fc_job.Proxy, "metric")
    fc_instance = module.fc_module.Create("test")
    fc_instance.ToolController = tc

    for param in module.param_mapping.values():
        enumeration = None

        if isinstance(param, AutoUnitKey):
            param = param.key
        elif isinstance(param, tuple):
            param, enumeration = param

        assert hasattr(fc_instance, param)
