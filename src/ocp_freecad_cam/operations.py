"""
Operation abstractions that interface directly with FreeCAD API

Developer notes:
- Setting Operation.Base resets some (?) properties
- Pocket 3D appears to be buggy, https://github.com/FreeCAD/FreeCAD/issues/6815 possibly related


"""

from abc import ABC
from typing import TYPE_CHECKING, Literal

import Part
import Path.Base.SetupSheet as PathSetupSheet
from Path.Op import MillFace, PocketShape, Profile

if TYPE_CHECKING:
    from api import Job


class Op(ABC):
    def __init__(self, job: "Job", *args, name=None, **kwargs):
        self.job = job
        self.n = len(self.job.ops) + 1
        self.name = name

    def execute(self, doc):
        raise NotImplemented

    @property
    def label(self):
        if self.name:
            return self.name
        return f"{self.__class__.__name__}_{self.n}"


class AreaOp(Op, ABC):
    def __init__(
        self,
        job: "Job",
        face_count: int,
        edge_count: int,
        vertex_count: int,
        compound_brep: str,
        *args,
        **kwargs,
    ):
        super().__init__(job, *args, **kwargs)
        self.face_count = face_count
        self.edge_count = edge_count
        self.vertex_count = vertex_count
        self.compound_brep = compound_brep

    def fc_op(self, base_features):
        raise NotImplemented

    def execute(self, doc):
        fc_compound = Part.Compound()
        fc_compound.importBrepFromString(self.compound_brep)
        feature = doc.addObject("Part::Feature", f"op_brep_{self.n}")
        feature.Shape = fc_compound

        base_features = []
        sub_selectors = []

        for i in range(1, self.face_count + 1):
            sub_selectors.append(f"Face{i}")
        for i in range(1, self.edge_count + 1):
            sub_selectors.append(f"Edge{i}")
        for i in range(1, self.vertex_count + 1):
            sub_selectors.append(f"Vertex{i}")

        base_features.append((feature, tuple(sub_selectors)))

        fc_op = self.fc_op(base_features)
        fc_op.Proxy.execute(fc_op)


class ProfileOp(AreaOp):
    kwargs_mapping = {
        "side": {
            "in": "Inside",
            "out": "Outside",
        }
    }

    def __init__(self, job: "Job", *args, side: Literal["Inside", "Outside"], **kwargs):
        super().__init__(job, *args, **kwargs)
        self.side = side

    def fc_op(self, base_features):
        name = self.label
        PathSetupSheet.RegisterOperation(name, Profile.Create, Profile.SetupProperties)
        fc_op = Profile.Create(name)
        fc_op.Base = base_features
        fc_op.Side = self.side
        return fc_op


class FaceOp(AreaOp):
    def __init__(self, *args, finish_depth=0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.finish_depth = finish_depth

    def fc_op(self, base_features):
        name = self.label
        PathSetupSheet.RegisterOperation(
            name, MillFace.Create, MillFace.SetupProperties
        )
        fc_op = MillFace.Create(name)
        fc_op.Base = base_features
        fc_op.BoundaryShape = "Stock"
        fc_op.FinishDepth = self.finish_depth
        return fc_op


class PocketOp(AreaOp):
    """2.5D pocket op"""

    def __init__(self, *args, finish_depth=0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.finish_depth = finish_depth

    def fc_op(self, base_features):
        name = self.label
        PathSetupSheet.RegisterOperation(
            name, PocketShape.Create, PocketShape.SetupProperties
        )
        fc_op = PocketShape.Create(name)
        fc_op.Base = base_features
        fc_op.FinishDepth = self.finish_depth
        return fc_op
