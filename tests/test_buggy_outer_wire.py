import os
from io import BytesIO

import cadquery as cq
import pytest
from OCP.ShapeAnalysis import ShapeAnalysis
from OCP.ShapeFix import ShapeFix_Shape


@pytest.fixture
def buggy_face():
    base_path = os.path.dirname(__file__)
    with open(os.path.join(base_path, "face_with_buggy_outer_wire.brep"), "r") as f:
        brep = BytesIO(f.read().encode("utf8"))
    face = cq.Face.importBrep(brep)
    return face


def test_occt_shape_analysis_outer_wire_bug(buggy_face):
    wrong_wire = cq.Wire(ShapeAnalysis.OuterWire_s(buggy_face.wrapped))
    assert buggy_face.outerWire().Length() != wrong_wire.Length()

    buggy_compound = cq.Compound.makeCompound([buggy_face])
    sf = ShapeFix_Shape(buggy_compound.wrapped)
    sf.Perform()
    fixed_compound = cq.Compound(sf.Shape())
    correct_wire = cq.Wire(ShapeAnalysis.OuterWire_s(fixed_compound.Faces()[0].wrapped))
    assert buggy_face.outerWire().Length() == correct_wire.Length()
