"""
Operation abstractions that interface directly with FreeCAD API

Developer notes:
- Setting Operation.Base resets some (?) properties
- Pocket 3D appears to be buggy, https://github.com/FreeCAD/FreeCAD/issues/6815 possibly related


"""

from abc import ABC
from typing import TYPE_CHECKING, Literal, Optional

import Part
import Path.Base.SetupSheet as PathSetupSheet
import Path.Base.Util as PathUtil
import PathScripts.PathUtils as PathUtils
from Path.Dressup import Boundary, DogboneII, Tags
from Path.Op import Drilling, MillFace, PocketShape, Profile

from ocp_freecad_cam.api_util import apply_params, map_params

if TYPE_CHECKING:
    from api import Job


class Op(ABC):
    def __init__(
        self,
        job: "Job",
        *args,
        tool_controller,
        face_count: int,
        edge_count: int,
        vertex_count: int,
        compound_brep: str,
        name=None,
        dressups: Optional[list["Dressup"]] = None,
    ):
        self.job = job
        self.n = len(self.job.ops) + 1
        self.name = name
        self.tool_controller = tool_controller
        self.face_count = face_count
        self.edge_count = edge_count
        self.vertex_count = vertex_count
        self.compound_brep = compound_brep
        self.dressups = dressups or []

    def execute(self, doc):
        base_features = self.create_base_features(doc)
        fc_op = self.create_operation(base_features)
        fc_op.ToolController = self.tool_controller
        fc_op.Proxy.execute(fc_op)
        self.create_dressups(fc_op)

    def create_base_features(self, doc):
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
        return base_features

    def create_operation(self, base_features):
        raise NotImplemented

    def create_dressups(self, fc_op):
        base = fc_op
        for dressup in self.dressups:
            fc_dressup = dressup.create(base)
            for k, v in dressup.params:
                PathUtil.setProperty(fc_dressup, k, v)
            fc_dressup.Proxy.execute(fc_dressup)
            base = fc_dressup

    @property
    def label(self):
        if self.name:
            return self.name
        return f"{self.__class__.__name__}_{self.n}"


class AreaOp(Op, ABC):
    def __init__(
        self,
        job: "Job",
        *args,
        **kwargs,
    ):
        super().__init__(job, *args, **kwargs)


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

    def create_operation(self, base_features):
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

    def create_operation(self, base_features):
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

    def create_operation(self, base_features):
        name = self.label
        PathSetupSheet.RegisterOperation(
            name, PocketShape.Create, PocketShape.SetupProperties
        )
        fc_op = PocketShape.Create(name)
        fc_op.Base = base_features
        fc_op.FinishDepth = self.finish_depth
        return fc_op


class DrillOp(Op):
    param_mapping = {
        "add_tip_length": "AddTipLength",
        "dwell_time": "DwellTime",
        "dwell_enabled": "DwellEnabled",
        "extra_offset": "ExtraOffset",
        "keep_tool_down": "KeepToolDown",
        "peck_depth": "PeckDepth",
        "peck_enabled": "PeckEnabled",
        "retract_height": "RetractHeight",
        "retract_mode": "RetractMode",
        "chip_break_enabled": "chipBreakEnabled",
    }

    def __init__(
        self,
        job: "Job",
        *args,
        dwell_time: Optional[float] = None,
        extra_offset: Optional[float] = None,
        peck_depth: Optional[float] = None,
        keep_tool_down: Optional[bool] = None,
        retract_height: Optional[bool] = None,
        chip_break_enabled: Optional[bool] = None,
        **kwargs,
    ):
        """
        Attributes in FreeCAD but not here:
        * RetractMode is overriden by KeepToolDown
        * AddTipLength is not used anywhere
        """

        super().__init__(job, *args, **kwargs)
        dwell_enabled = None if dwell_time is None else dwell_time > 0
        peck_enabled = None if peck_depth is None else peck_depth > 0

        self.params = map_params(
            self.param_mapping,
            dwell_time=dwell_time,
            dwell_enabled=dwell_enabled,
            extra_offset=extra_offset,
            keep_tool_down=keep_tool_down,
            peck_depth=peck_depth,
            peck_enabled=peck_enabled,
            retract_height=retract_height,
            chip_break_enabled=chip_break_enabled,
        )

    def create_operation(self, base_features):
        name = self.label
        PathSetupSheet.RegisterOperation(
            name, Drilling.Create, Drilling.SetupProperties
        )
        fc_op = Drilling.Create(name)
        fc_op.Base = base_features
        apply_params(fc_op, self.params)

        return fc_op


class Dressup:
    factory = None
    params = None

    def create(self, base):
        return self.factory.Create(base)


class Dogbone(Dressup):
    factory = DogboneII
    mapping = {
        "incision": "Incision",
        "custom": "Custom",
        "side": "Side",
        "style": (
            "Style",
            {
                "dogbone": "Dogbone",
                "thor": "T-bone horizontal",
                "tver": "T-bone vertical",
                "tlong": "T-bone long edge",
                "tshort": "T-bone short edge",
            },
        ),
    }

    def __init__(
        self,
        incision: Optional[Literal["adaptive", "fixed", "custom"]] = None,
        custom: Optional[float] = None,
        side: Optional[Literal["left", "right"]] = None,
        style: Optional[Literal["dogbone", "thor", "tver", "tlong", "tshort"]] = None,
    ):
        self.params = map_params(
            self.mapping, incision=incision, custom=custom, side=side, style=style
        )

    def create(self, base):
        # DogboneII has this required code that exists only on the GUI side
        fc_obj = super().create(base)
        job = PathUtils.findParentJob(base)
        job.Proxy.addOperation(fc_obj, base)
        return fc_obj


class Tab(Dressup):
    factory = Tags
    mapping = {
        "angle": "Angle",
        "height": "Height",
        "width": "Width",
        "positions": "Positions",
        "disabled": "Disabled",
        "fillet_radius": "Radius",
        "segmentation_factor": "SegmentationFactor",
    }

    def __init__(
        self,
        angle=None,
        height=None,
        width=None,
        positions=None,
        disabled=None,
        fillet_radius=None,
        segmentation_factor=None,
    ):
        self.params = map_params(
            self.mapping,
            angle=angle,
            height=height,
            width=width,
            positions=positions,
            disabled=disabled,
            fillet_radius=fillet_radius,
            segmentation_factor=segmentation_factor,
        )


class Boundary(Dressup):
    factory = Boundary

    # TODO
