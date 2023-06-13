"""
Operation abstractions that interface directly with FreeCAD API

Developer notes:
- Setting Operation.Base resets some (?) properties
- Pocket 3D appears to be buggy, https://github.com/FreeCAD/FreeCAD/issues/6815 possibly related


"""

from abc import ABC
from types import ModuleType
from typing import TYPE_CHECKING, Literal, Optional

import Part
import Path.Base.SetupSheet as PathSetupSheet
import Path.Base.Util as PathUtil
import PathScripts.PathUtils as PathUtils
from Path.Dressup import Boundary, DogboneII, Tags
from Path.Op import Drilling, Helix, MillFace, PocketShape, Profile

from ocp_freecad_cam.api_util import ParamMapping, apply_params, map_params

if TYPE_CHECKING:
    from api import Job


class Op(ABC):
    fc_module: ModuleType
    params: ParamMapping

    def __init__(
        self,
        job: "Job",
        *,
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
        name = self.label
        PathSetupSheet.RegisterOperation(
            name, self.fc_module.Create, self.fc_module.SetupProperties
        )
        fc_op = self.fc_module.Create(name)
        fc_op.Base = base_features
        apply_params(fc_op, self.params)
        return fc_op

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
    fc_module = Profile
    param_mapping = {
        "side": (
            "Side",
            {
                "in": "Inside",
                "out": "Outside",
            },
        ),
        "direction": (
            "Direction",
            {
                "cw": "CW",
                "ccw": "CCW",
            },
        ),
        "handle_multiple_features": (
            "HandleMultipleFeatures",
            {
                "collectively": "Collectively",
                "individually": "Individually",
            },
        ),
        "offset_extra": "OffsetExtra",
        "use_comp": "UseComp",
        "process_circles": "processCircles",
        "process_holes": "processHoles",
        "process_perimeter": "processPerimeter",
    }

    def __init__(
        self,
        *args,
        side: Literal["in", "out"],
        direction: Literal["cw", "ccw"],
        handle_multiple_features: Literal["collectively", "individually"],
        offset_extra: float,
        use_comp: bool,
        process_circles: bool,
        process_holes: bool,
        process_perimeter: bool,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.params = map_params(
            self.param_mapping,
            side=side,
            direction=direction,
            handle_multiple_features=handle_multiple_features,
            offset_extra=offset_extra,
            use_comp=use_comp,
            process_circles=process_circles,
            process_holes=process_holes,
            process_perimeter=process_perimeter,
        )


class FaceOp(AreaOp):
    fc_module = MillFace

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
    fc_module = PocketShape
    param_mapping = {
        "finish_depth": "FinishDepth",
        "pattern": (
            "OffsetPattern",
            {
                "zigzag": "ZigZag",
                "offset": "Offset",
                "zigzag_offset": "ZigZagOffset",
                "line": "Line",
                "grid": "Grid,",
            },
        ),
        "cut_mode": ("CutMode", {"climb": "Climb", "conventional": "Conventional"}),
        "extra_offset": "ExtraOffset",
        "keep_tool_down": "KeepToolDown",
        "min_travel": "MinTravel",
        "pocket_last_stepover": "PocketLastStepOver",
        "start_at": (
            "StartAt",
            {
                "center": "Center",
                "edge": "Edge",
            },
        ),
        "step_over": "StepOver",
        "use_outline": "UseOutline",
        "zigzag_angle": "ZigZagAngle",
    }

    def __init__(
        self,
        *args,
        finish_depth: float,
        pattern: Literal["zigzag", "offset", "zigzag_offset", "line", "grid"],
        cut_mode: Literal["climb", "conventional"],
        extra_offset: float,
        keep_tool_down: bool,
        min_travel: bool,
        pocket_last_stepover: float,
        start_at: Literal["center", "edge"],
        step_over: float,
        use_outline: bool,
        zigzag_angle: float,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.params = map_params(
            self.param_mapping,
            pattern=pattern,
            cut_mode=cut_mode,
            extra_offset=extra_offset,
            keep_tool_down=keep_tool_down,
            min_travel=min_travel,
            pocket_last_stepover=pocket_last_stepover,
            start_at=start_at,
            step_over=step_over,
            use_outline=use_outline,
            zigzag_angle=zigzag_angle,
        )


class DrillOp(Op):
    fc_module = Drilling

    param_mapping = {
        "dwell_time": "DwellTime",
        "dwell_enabled": "DwellEnabled",
        "extra_offset": "ExtraOffset",
        "keep_tool_down": "KeepToolDown",
        "peck_depth": "PeckDepth",
        "peck_enabled": "PeckEnabled",
        "retract_height": "RetractHeight",
        "chip_break_enabled": "chipBreakEnabled",
    }

    def __init__(
        self,
        *args,
        dwell_time: Optional[float],
        extra_offset: Optional[float],
        peck_depth: Optional[float],
        keep_tool_down: Optional[bool],
        retract_height: Optional[bool],
        chip_break_enabled: Optional[bool],
        **kwargs,
    ):
        """
        Attributes in FreeCAD but not here:
        * RetractMode is overriden by KeepToolDown in FC code
        * AddTipLength is not used anywhere?
        """

        super().__init__(*args, **kwargs)
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


class HelixOp(Op):
    param_mapping = {
        "direction": "Direction",
        "offset_extra": "OffsetExtra",
        "start_radius": "StartRadius",
        "start_side": ("StartSide", {"out": "Outside", "in": "Inside"}),
        "step_over": "StepOver",
    }

    def __init__(
        self,
        job: "Job",
        direction: Optional[Literal["CW", "CCW"]] = None,
        offset_extra: Optional[float] = None,
        start_radius: Optional[float] = None,
        start_side: Optional[Literal["out", "in"]] = None,
        step_over: Optional[float] = None,
        **kwargs,
    ):
        super().__init__(job, **kwargs)
        self.params = map_params(
            self.param_mapping,
            direction=direction,
            offset_extra=offset_extra,
            start_radius=start_radius,
            start_side=start_side,
            step_over=step_over,
        )

    def create_operation(self, base_features):
        name = self.label
        PathSetupSheet.RegisterOperation(name, Helix.Create, Helix.SetupProperties)
        fc_op = Helix.Create(name)
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
