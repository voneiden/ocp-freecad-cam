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
    FaceLegacyOp,
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
    feature = fc_doc.addObject("Part::Feature", "root_brep")
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


OP_PARAMS = [
    (ProfileOp, endmill_tc),
    (FaceLegacyOp, endmill_tc),
    (FaceOp, endmill_tc),
    (PocketOp, endmill_tc),
    (DrillOp, endmill_tc),
    (HelixOp, endmill_tc),
    (DeburrOp, endmill_tc),
    (VCarveOp, vbit_tc),
    (Surface3DOp, endmill_tc),
]


def _mapped_fc_prop_names(module) -> set[str]:
    """Return the set of FC property names referenced in a module's param_mapping,
    including the base Op class private mapping (e.g. CoolantMode)."""
    from ocp_freecad_cam.fc_impl import Op

    names = set()
    for mapping in (module.param_mapping, Op._Op__param_mapping):
        for param in mapping.values():
            if isinstance(param, AutoUnitKey):
                names.add(param.key)
            elif isinstance(param, tuple):
                names.add(param[0])
            else:
                names.add(param)
    return names


@pytest.mark.parametrize("module,tc_f", OP_PARAMS)
def test_params(fc_job, module, tc_f):
    tc = tc_f(fc_job.Proxy, "metric")
    fc_instance = module.fc_module.Create("test")
    fc_instance.ToolController = tc

    for param in module.param_mapping.values():
        if isinstance(param, AutoUnitKey):
            fc_prop = param.key
            assert hasattr(fc_instance, fc_prop), f"FC property '{fc_prop}' not found"
        elif isinstance(param, tuple):
            fc_prop, value_dict = param
            assert hasattr(fc_instance, fc_prop), f"FC property '{fc_prop}' not found"
            fc_choices = set(fc_instance.getEnumerationsOfProperty(fc_prop))
            our_choices = set(value_dict.values())
            assert our_choices == fc_choices, (
                f"'{fc_prop}' enum mismatch: "
                f"extra in ours={our_choices - fc_choices}, "
                f"missing from ours={fc_choices - our_choices}"
            )
        else:
            assert hasattr(fc_instance, param), f"FC property '{param}' not found"


@pytest.mark.parametrize("module,tc_f", OP_PARAMS)
def test_enum_coverage(fc_job, module, tc_f):
    """All FC PropertyEnumeration properties must appear in param_mapping."""
    tc = tc_f(fc_job.Proxy, "metric")
    fc_instance = module.fc_module.Create("test")
    fc_instance.ToolController = tc

    mapped = _mapped_fc_prop_names(module)
    unmapped = [
        p
        for p in fc_instance.PropertiesList
        if "Enumeration" in fc_instance.getTypeIdOfProperty(p) and p not in mapped
    ]
    assert not unmapped, (
        f"{module.__name__} has unmapped FC enum properties: {unmapped}"
    )
