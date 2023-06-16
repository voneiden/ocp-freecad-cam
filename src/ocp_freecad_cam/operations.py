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
from Path.Dressup import Boundary
from Path.Op import Deburr, Drilling, Helix, MillFace, PocketShape, Profile, Surface
from Path.Op import Vcarve as FCVCarve

from ocp_freecad_cam.api_util import AutoUnitKey, ParamMapping, apply_params, map_params

if TYPE_CHECKING:
    from api import Job


class Op(ABC):
    fc_module: ModuleType
    params: ParamMapping

    def __init__(
        self,
        job: "Job",
        *,
        tool,
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
        self.tool = tool
        self.face_count = face_count
        self.edge_count = edge_count
        self.vertex_count = vertex_count
        self.compound_brep = compound_brep
        self.dressups = dressups or []

    def execute(self, doc):
        base_features = self.create_base_features(doc)
        op_tool_controller = self.tool.tool_controller(self.job.fc_job, self.job.units)
        fc_op = self.create_operation(base_features)
        fc_op.ToolController = op_tool_controller
        fc_op.Proxy.execute(fc_op)
        self.create_dressups(fc_op)

    def create_base_features(self, doc):
        if self.compound_brep is None:
            return []

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
        apply_params(fc_op, self.params, self.job.units)
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
        "offset_extra": AutoUnitKey("OffsetExtra"),
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
    param_mapping = {
        "finish_depth": AutoUnitKey("FinishDepth"),
        "boundary": (
            "BoundaryShape",
            {
                "boundbox": "Boundbox",
                "face": "Face Region",
                "perimeter": "Perimeter",
                "stock": "Stock",
            },
        ),
        "clear_edges": "ClearEdges",
        "exclude_raised": "ExcludeRaisedAreas",
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
    }

    def __init__(
        self,
        *args,
        finish_depth: float,
        boundary: Literal["boundbox", "face", "perimeter", "stock"],
        clear_edges: bool,
        exclude_raised: bool,
        pattern: Literal["zigzag", "offset", "zigzag_offset", "line", "grid"],
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.params = map_params(
            self.param_mapping,
            finish_depth=finish_depth,
            boundary=boundary,
            clear_edges=clear_edges,
            exclude_raised=exclude_raised,
            pattern=pattern,
        )


class PocketOp(AreaOp):
    fc_module = PocketShape
    param_mapping = {
        "finish_depth": AutoUnitKey("FinishDepth"),
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
        "extra_offset": AutoUnitKey("ExtraOffset"),
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
            finish_depth=finish_depth,
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
        "extra_offset": (
            "ExtraOffset",
            {"none": "None", "1x": "Drill Tip", "2x": "2x Drill Tip"},
        ),
        "keep_tool_down": "KeepToolDown",
        "peck_depth": AutoUnitKey("PeckDepth"),
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


class HelixOp(Op):
    fc_module = Helix
    param_mapping = {
        "direction": ("Direction", {"cw": "CW", "ccw": "CCW"}),
        "offset_extra": AutoUnitKey("OffsetExtra"),
        "start_radius": "StartRadius",
        "start_side": ("StartSide", {"out": "Outside", "in": "Inside"}),
        "step_over": "StepOver",
    }

    def __init__(
        self,
        *args,
        direction: Optional[Literal["cw", "ccw"]],
        offset_extra: Optional[float],
        start_radius: Optional[float],
        start_side: Optional[Literal["out", "in"]],
        step_over: Optional[float],
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.params = map_params(
            self.param_mapping,
            direction=direction,
            offset_extra=offset_extra,
            start_radius=start_radius,
            start_side=start_side,
            step_over=step_over,
        )


# class Engrave(Op):
#    fc_module = FCEngrave


class DeburrOp(Op):
    fc_module = Deburr
    param_mapping = {
        "width": AutoUnitKey("Width"),
        "extra_depth": AutoUnitKey("ExtraDepth"),
        "direction": ("Direction", {"cw": "CW", "ccw": "CCW"}),
        "entry_point": "EntryPoint",
    }

    def __init__(
        self,
        *args,
        width: float,
        extra_depth: float,
        direction: Literal["cw", "ccw"],
        entry_point: int,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.params = map_params(
            self.param_mapping,
            width=width,
            extra_depth=extra_depth,
            direction=direction,
            entry_point=entry_point,
        )


class VCarveOp(Op):
    fc_module = FCVCarve
    param_mapping = {
        "discretize": "Discretize",
        "colinear": "Colinear",
    }

    def __init__(self, *args, discretize: float, colinear: float, **kwargs):
        super().__init__(*args, **kwargs)
        self.params = map_params(
            self.param_mapping, discretize=discretize, colinear=colinear
        )


class Surface3DOp(Op):
    fc_module = Surface
    param_mapping = {
        "bound_box": ("BoundBox", {"base_bound_box": "BaseBoundBox", "stock": "Stock"}),
        "cut_mode": ("CutMode", {"climb": "Climb", "conventional": "Conventional"}),
        "cut_pattern": (
            "CutPattern",
            {
                "line": "Line",
                "circular": "Circular",
                "circular_zig_zag": "CircularZigZag",
                "offset": "Offset",
                "spiral": "Spiral",
                "zigzag": "ZigZag",
            },
        ),
        "cut_pattern_angle": "CutPatternAngle",
        "cut_pattern_reversed": "CutPatternReversed",
        "depth_offset": AutoUnitKey("DepthOffset"),
        "layer_mode": ("LayerMode", {"single": "Single-pass", "multi": "Multi-pass"}),
        "profile_edges": (
            "ProfileEdges",
            {"none": "None", "only": "Only", "first": "First", "last": "Last"},
        ),
        "sample_interval": "SampleInterval",
        "step_over": "StepOver",
        "angular_deflection": AutoUnitKey("AngularDeflection"),
        "linear_deflection": AutoUnitKey("LinearDeflection"),
        "circular_use_g2g3": "CircularUseG2G3",
        "gap_threshold": AutoUnitKey("GapThreshold"),
        "optimize_linear_paths": "OptimizeLinearPaths",
        "optimize_step_over_transitions": "OptimizeStepOverTransitions",
        "avoid_last_x_faces": "AvoidLastX_Faces",
        "avoid_last_x_internal_features": "AvoidLastX_InternalFeatures",
        "boundary_adjustment": AutoUnitKey("BoundaryAdjustment"),
        "boundary_enforcement": "BoundaryEnforcement",
        "multiple_features": (
            "HandleMultipleFeatures",
            {"collectively": "Collectively", "individually": "Individually"},
        ),
        "internal_features_adjustment": AutoUnitKey("InternalFeaturesAdjustment"),
        "internal_features_cut": "InternalFeaturesCut",
        "start_point": AutoUnitKey("StartPoint"),
        "scan_type": ("ScanType", {"planar": "Planar", "rotational": "Rotational"}),
    }

    def __init__(
        self,
        *args,
        bound_box: Literal["base_bound_box", "stock"],
        cut_mode: Literal["climb", "conventional"],
        cut_pattern: Literal[
            "line", "circular", "circular_zig_zag", "offset", "spiral", "zigzag"
        ],
        cut_pattern_angle: float,
        cut_pattern_reversed: bool,
        depth_offset: float,
        layer_mode: Literal["single", "multi"],
        profile_edges: Literal["none", "only", "first", "last"],
        sample_interval: float | str,
        step_over: float,
        angular_deflection: float | str,
        linear_deflection: float | str,
        circular_use_g2g3: bool,
        gap_threshold: float | str,
        optimize_linear_paths: bool,
        optimize_step_over_transitions: bool,
        avoid_last_x_faces: int,
        avoid_last_x_internal_features: bool,
        boundary_adjustment: float | str,
        boundary_enforcement: bool,
        multiple_features: Literal["collectively", "individually"],
        internal_features_adjustment: float | str,
        internal_features_cut: bool,
        start_point: tuple[float | str, float | str, float | str],
        scan_type: Literal["planar", "rotational"],
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.params = map_params(
            self.param_mapping,
            bound_box=bound_box,
            cut_mode=cut_mode,
            cut_pattern=cut_pattern,
            cut_pattern_angle=cut_pattern_angle,
            cut_pattern_reversed=cut_pattern_reversed,
            depth_offset=depth_offset,
            layer_mode=layer_mode,
            profile_edges=profile_edges,
            sample_interval=sample_interval,
            step_over=step_over,
            angular_deflection=angular_deflection,
            linear_deflection=linear_deflection,
            circular_use_g2g3=circular_use_g2g3,
            gap_threshold=gap_threshold,
            optimize_linear_paths=optimize_linear_paths,
            optimize_step_over_transitions=optimize_step_over_transitions,
            avoid_last_x_faces=avoid_last_x_faces,
            avoid_last_x_internal_features=avoid_last_x_internal_features,
            boundary_adjustment=boundary_adjustment,
            boundary_enforcement=boundary_enforcement,
            multiple_features=multiple_features,
            internal_features_adjustment=internal_features_adjustment,
            internal_features_cut=internal_features_cut,
            start_point=start_point,
            scan_type=scan_type,
        )


class Dressup:
    factory = None
    params = None

    def create(self, base):
        return self.factory.Create(base)


class Boundary(Dressup):
    factory = Boundary

    # TODO
