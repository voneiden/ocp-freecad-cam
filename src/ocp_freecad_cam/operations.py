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
    def __init__(self, job: "Job", breps: list[str], *args, **kwargs):
        super().__init__(job, *args, **kwargs)
        self.op_breps = breps

    def fc_op(self, base_features):
        raise NotImplemented

    def execute(self, doc):
        base_features = []
        for i, brep in enumerate(self.op_breps):
            fc_compound = Part.Face()
            fc_compound.importBrepFromString(brep)
            feature = doc.addObject("Part::Feature", f"brep_{self.n}_{i}")
            feature.Shape = fc_compound
            base_features.append((feature, ("Face1",)))
        fc_op = self.fc_op(base_features)
        print("BEFORE", getattr(fc_op, "Side", "-"))
        fc_op.Proxy.execute(fc_op)
        print("AFTER", getattr(fc_op, "Side", "-"))


class ProfileOp(AreaOp):
    def __init__(self, job: "Job", *args, side: Literal["Inside", "Outside"], **kwargs):
        super().__init__(job, *args, **kwargs)
        self.side = side

    def fc_op(self, base_features):
        name = self.label
        PathSetupSheet.RegisterOperation(name, Profile.Create, Profile.SetupProperties)
        fc_op = Profile.Create(name)
        fc_op.Base = base_features
        print("SET FC_OP to", self.side)
        fc_op.Side = self.side
        print("FC_OP set to", fc_op.Side)
        return fc_op


class FaceOp(AreaOp):
    def fc_op(self, base_features):
        name = self.label
        PathSetupSheet.RegisterOperation(
            name, MillFace.Create, MillFace.SetupProperties
        )
        fc_op = MillFace.Create(name)
        fc_op.Base = base_features
        fc_op.BoundaryShape = "Stock"
        return fc_op


class PocketOp(AreaOp):
    """2.5D pocket op"""

    def fc_op(self, base_features):
        name = self.label
        PathSetupSheet.RegisterOperation(
            name, PocketShape.Create, PocketShape.SetupProperties
        )
        fc_op = PocketShape.Create(name)
        fc_op.Base = base_features
        return fc_op
