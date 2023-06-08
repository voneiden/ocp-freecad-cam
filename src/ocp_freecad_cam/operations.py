from abc import ABC
from typing import TYPE_CHECKING

import Part
import Path.Base.SetupSheet as PathSetupSheet
from Path.Op import MillFace, PocketShape

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

    def fc_op(self):
        raise NotImplemented

    def execute(self, doc):
        op_features = []
        for i, brep in enumerate(self.op_breps):
            fc_compound = Part.Face()
            fc_compound.importBrepFromString(brep)
            feature = doc.addObject("Part::Feature", f"brep_{self.n}_{i}")
            feature.Shape = fc_compound
            op_features.append((feature, ("Face1",)))
        fc_op = self.fc_op()
        fc_op.Base = op_features
        fc_op.Proxy.execute(fc_op)


class PocketOp(AreaOp):
    """2.5D pocket op"""

    def fc_op(self):
        name = self.label
        PathSetupSheet.RegisterOperation(
            name, PocketShape.Create, PocketShape.SetupProperties
        )
        return PocketShape.Create(name)


class FaceOp(AreaOp):
    def fc_op(self):
        name = self.label
        PathSetupSheet.RegisterOperation(
            name, MillFace.Create, MillFace.SetupProperties
        )
        fc_op = MillFace.Create(name)
        fc_op.BoundaryShape = "Stock"
        return fc_op
