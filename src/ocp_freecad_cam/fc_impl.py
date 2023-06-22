"""
Operation abstractions that interface directly with FreeCAD API

Developer notes:
- Setting Operation.Base resets some (?) properties
- Pocket 3D appears to be buggy, https://github.com/FreeCAD/FreeCAD/issues/6815 possibly related


"""
import tempfile
from abc import ABC
from copy import copy
from types import ModuleType
from typing import TYPE_CHECKING, Literal, Optional

import FreeCAD
import Part
import Path.Base.SetupSheet as PathSetupSheet
import Path.Base.Util as PathUtil
from OCP.gp import gp_Pln
from OCP.TopoDS import TopoDS_Compound
from Path.Dressup import Boundary
from Path.Main import Job as FCJob
from Path.Main import Stock as FCStock
from Path.Op import (
    Adaptive,
    Deburr,
    Drilling,
    Engrave,
    Helix,
    MillFace,
    PocketShape,
    Profile,
    Surface,
)
from Path.Op import Vcarve as FCVCarve
from Path.Op import Waterline
from Path.Post.Command import buildPostList
from Path.Post.Processor import PostProcessor as FCPostProcessor

from ocp_freecad_cam.api_util import (
    AutoUnitKey,
    CompoundData,
    ParamMapping,
    apply_params,
    map_params,
    scale_shape,
    shape_to_brep,
    transform_shape,
)
from ocp_freecad_cam.common import PostProcessor
from ocp_freecad_cam.fc_impl_util import calculate_transforms
from ocp_freecad_cam.visualizer import visualize_fc_job

if TYPE_CHECKING:
    from api import Job  # noqa


class JobImpl:
    _job_param_mapping = {"geometry_tolerance": "GeometryTolerance"}
    _setup_sheet_param_mapping = {
        "coolant": "CoolantMode",
        "final_depth_expression": "FinalDepthExpression",
        "start_depth_expression": "StartDepthExpression",
        "step_down_expression": "StepDownExpression",
        "clearance_height_expression": "ClearanceHeightExpression",
        "clearance_height_offset": AutoUnitKey("ClearanceHeightOffset"),
        "safe_height_expression": "SafeHeightExpression",
        "safe_height_offset": AutoUnitKey("SafeHeightOffset"),
    }

    def __init__(
        self,
        *,
        top: gp_Pln,
        model: TopoDS_Compound,
        post_processor: Optional[PostProcessor],
        units: Literal["metric", "imperial"],
        geometry_tolerance,
        coolant,
        final_depth_expression,
        start_depth_expression,
        step_down_expression,
        clearance_height_expression,
        clearance_height_offset,
        safe_height_expression,
        safe_height_offset,
        stock,
    ):
        self.top = top
        self.forward, self.backward = calculate_transforms(top)
        self.units = units

        self.model = model
        transformed_job_model = transform_shape(model, self.forward)
        if sf := self.scale_factor:
            transformed_job_model = scale_shape(transformed_job_model, sf)

        self.model_brep = shape_to_brep(transformed_job_model)

        self.post_processor = post_processor

        self.job_params = map_params(
            self._job_param_mapping, geometry_tolerance=geometry_tolerance
        )

        self.setup_sheet_params = map_params(
            self._setup_sheet_param_mapping,
            coolant=coolant,
            final_depth_expression=final_depth_expression,
            start_depth_expression=start_depth_expression,
            step_down_expression=step_down_expression,
            clearance_height_expression=clearance_height_expression,
            clearance_height_offset=clearance_height_offset,
            safe_height_expression=safe_height_expression,
            safe_height_offset=safe_height_offset,
        )

        self.stock = stock
        self.doc = None
        self.ops = []

    @property
    def scale_factor(self):
        if self.units == "metric":
            return None
        elif self.units == "imperial":
            return 25.4
        raise ValueError(f"Unknown unit: ({self.units})")

    def _set_active(self):
        FreeCAD.setActiveDocument(self.doc.Name)

    def _build(self, rebuild=False):
        if self.doc:
            if not rebuild:
                return
            FreeCAD.closeDocument(self.doc)

        self.doc = FreeCAD.newDocument("ocp_freecad_cam")
        self._set_active()
        fc_compound = Part.Compound()
        fc_compound.importBrepFromString(self.model_brep)
        feature = self.doc.addObject("Part::Feature", f"root_brep")
        feature.Shape = fc_compound

        fc_job = FCJob.Create("Job", [feature])
        self.fc_job = fc_job

        apply_params(self.fc_job, self.job_params, self.units)
        setup_sheet = self.fc_job.SetupSheet
        apply_params(setup_sheet, self.setup_sheet_params, self.units)

        if self.stock:
            self.stock.create_stock(self)

        # Remove default tools as we'll create our own later
        # Necessary also because of  buggy FX implementation
        tools = [tool for tool in self.fc_job.Tools.Group]
        for tool in tools:
            self.fc_job.Tools.removeObject(tool)
        if self.post_processor:
            fc_job.PostProcessor = self.post_processor

        for op in self.ops:
            op.execute(self)

        self.doc.recompute()

    def save_fcstd(self, filename, rebuild=False):
        self._build(rebuild)
        self.doc.saveAs(filename)

    def to_gcode(self, rebuild=False):
        if self.post_processor is None:
            raise ValueError(
                "No postprocessor set - set Job postprocessor to a valid value"
            )
        self._build(rebuild)
        postlist = buildPostList(self.fc_job)
        processor = FCPostProcessor.load(self.fc_job.PostProcessor)

        for idx, section in enumerate(postlist):
            name, sublist = section
            with tempfile.NamedTemporaryFile() as tmp_file:
                options = ["--no-show-editor"]
                if self.units == "imperial":
                    options.append("--inches")

                gcode = processor.export(sublist, tmp_file.name, " ".join(options))
                return gcode

    def show(self, show_object=None, rebuild=False):
        self._build(rebuild)
        return visualize_fc_job(self.fc_job, self.backward, show_object=show_object)

    def copy(self, ops):
        job_impl = copy(self)
        job_impl.doc = None
        job_impl.ops = ops
        return job_impl


class Op(ABC):
    fc_module: ModuleType
    params: ParamMapping

    __param_mapping = {
        "clearance_height": "ClearanceHeight",
        "final_depth": "FinalDepth",
        "safe_height": "SafeHeight",
        "start_depth": "StartDepth",
        "step_down": "StepDown",
        "coolant": "CoolantMode",
    }

    def __init__(
        self,
        *,
        tool,
        compound_data: CompoundData,
        name=None,
        # Expressions
        clearance_height=None,
        final_depth=None,
        safe_height=None,
        start_depth=None,
        step_down=None,
        coolant=None,
        dressups: Optional[list["Dressup"]] = None,
    ):
        self.name = name
        self.tool = tool
        self.compound_data = compound_data

        self.dressups = dressups or []
        self.__params = map_params(
            self.__param_mapping,
            clearance_height=clearance_height,
            final_depth=final_depth,
            safe_height=safe_height,
            start_depth=start_depth,
            step_down=step_down,
            coolant=coolant,
        )

    def n(self, job_impl: JobImpl):
        same_ops = [op for op in job_impl.ops if isinstance(op, self.__class__)]
        return same_ops.index(self) + 1

    def execute(self, job_impl: JobImpl):
        base_features = self.create_base_features(job_impl)

        op_tool_controller = self.tool.tool_controller(
            job_impl.fc_job.Proxy, job_impl.units
        )
        fc_op = self.create_operation(job_impl, base_features)
        apply_params(fc_op, self.__params, job_impl.units)
        fc_op.ToolController = op_tool_controller
        fc_op.Proxy.execute(fc_op)
        self.create_dressups(job_impl, fc_op)

    def create_base_features(self, job_impl: JobImpl):
        doc = job_impl.doc
        compound_brep = self.compound_data.to_transformed_brep(
            job_impl.forward, job_impl.scale_factor
        )
        if compound_brep is None:
            return []

        fc_compound = Part.Compound()
        fc_compound.importBrepFromString(compound_brep)
        feature = doc.addObject("Part::Feature", f"op_brep_{self.n(job_impl)}")
        feature.Shape = fc_compound

        base_features = []
        sub_selectors = []

        for i in range(1, self.compound_data.face_count + 1):
            sub_selectors.append(f"Face{i}")
        for i in range(1, self.compound_data.edge_count + 1):
            sub_selectors.append(f"Edge{i}")
        for i in range(1, self.compound_data.vertex_count + 1):
            sub_selectors.append(f"Vertex{i}")

        base_features.append((feature, tuple(sub_selectors)))
        return base_features

    def create_operation(self, job_impl: JobImpl, base_features):
        name = self.label(job_impl)
        PathSetupSheet.RegisterOperation(
            name, self.fc_module.Create, self.fc_module.SetupProperties
        )
        fc_op = self.fc_module.Create(name)
        fc_op.Base = base_features
        apply_params(fc_op, self.params, job_impl.units)
        return fc_op

    def create_dressups(self, job_impl, fc_op):
        base = fc_op
        for dressup in self.dressups:
            fc_dressup = dressup.create(job_impl, base)
            for k, v in dressup.params:
                PathUtil.setProperty(fc_dressup, k, v)
            fc_dressup.Proxy.execute(fc_dressup)
            base = fc_dressup

    def label(self, job_impl: JobImpl):
        if self.name:
            return self.name
        return f"{self.__class__.__name__}_{self.n(job_impl)}"


class ProfileOp(Op):
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


class FaceOp(Op):
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


class PocketOp(Op):
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


class EngraveOp(Op):
    fc_module = Engrave
    param_mapping = {"start_vertex": "StartVertex"}

    def __init__(self, *args, start_vertex: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.params = map_params(self.param_mapping, start_vertex=start_vertex)


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


class WaterlineOp(Op):
    fc_module = Waterline
    param_mapping = {
        "algorithm": (
            "Algorithm",
            {"ocl": "OCL Dropcutter", "experimental": "Experimental"},
        ),
        "bound_box": ("BoundBox", {"base": "BaseBoundBox", "stock": "Stock"}),
        "cut_mode": ("CutMode", {"climb": "Climb", "conventional": "Conventional"}),
        "depth_offset": AutoUnitKey("DepthOffset"),
        "layer_mode": ("LayerMode", {"single": "Single-pass", "multi": "Multi-pass"}),
        "sample_interval": AutoUnitKey("SampleInterval"),
        "angular_deflection": AutoUnitKey("AngularDeflection"),
        "linear_deflection": AutoUnitKey("LinearDeflection"),
    }

    def __init__(
        self,
        *args,
        algorithm: Literal["ocl", "experimental"],
        bound_box: Literal["base", "stock"],
        cut_mode: Literal["climb", "conventional"],
        depth_offset: float | str,
        layer_mode: Literal["single", "multi"],
        sample_interval: float | str,
        angular_deflection: float | str,
        linear_deflection: float | str,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.params = map_params(
            self.param_mapping,
            algorithm=algorithm,
            bound_box=bound_box,
            cut_mode=cut_mode,
            depth_offset=depth_offset,
            layer_mode=layer_mode,
            sample_interval=sample_interval,
            angular_deflection=angular_deflection,
            linear_deflection=linear_deflection,
        )


class AdaptiveOp(Op):
    fc_module = Adaptive
    param_mapping = {
        "finishing_profile": "FinishingProfile",
        "force_inside_cut": "ForceInsideCut",
        "helix_angle": "HelixAngle",
        "helix_cone_angle": "HelixConeAngle",
        "helix_diameter_limit": AutoUnitKey("HelixDiameterLimit"),
        "keep_tool_down_ratio": AutoUnitKey("KeepToolDownRatio"),
        "lift_distance": AutoUnitKey("LiftDistance"),
        "operation_type": (
            "OperationType",
            {"clearing": "Clearing", "profiling": "Profiling"},
        ),
        "side": ("Side", {"in": "Inside", "out": "Outside"}),
        "step_over": "StepOver",
        "stock_to_leave": AutoUnitKey("StockToLeave"),
        "tolerance": "Tolerance",
        "use_helix_arcs": "UseHelixArcs",
        "use_outline": "UseOutline",
    }

    def __init__(
        self,
        *args,
        finishing_profile: bool,
        force_inside_cut: bool,
        helix_angle: float,
        helix_cone_angle: float,
        helix_diameter_limit: float | str,
        keep_tool_down_ratio: float | str,
        lift_distance: float | str,
        operation_type: Literal["clearing", "profiling"],
        side: Literal["in", "out"],
        step_over: float,
        stock_to_leave: float | str,
        tolerance: float = 0,
        use_helix_arcs: bool,
        use_outline: bool,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.params = map_params(
            self.param_mapping,
            finishing_profile=finishing_profile,
            force_inside_cut=force_inside_cut,
            helix_angle=helix_angle,
            helix_cone_angle=helix_cone_angle,
            helix_diameter_limit=helix_diameter_limit,
            keep_tool_down_ratio=keep_tool_down_ratio,
            lift_distance=lift_distance,
            operation_type=operation_type,
            side=side,
            step_over=step_over,
            stock_to_leave=stock_to_leave,
            tolerance=tolerance,
            use_helix_arcs=use_helix_arcs,
            use_outline=use_outline,
        )


class Dressup:
    factory = None
    params = None

    def create(self, job_impl, base):
        return self.factory.Create(base)


class Boundary(Dressup):
    factory = Boundary

    # TODO


class StockBase(ABC):
    def create_stock(self, fc_job: FCJob):
        raise NotImplementedError


class Stock(StockBase):
    _param_mapping = {
        "xn": AutoUnitKey("ExtXneg"),
        "xp": AutoUnitKey("ExtXpos"),
        "yn": AutoUnitKey("ExtYneg"),
        "yp": AutoUnitKey("ExtYpos"),
        "zn": AutoUnitKey("ExtZneg"),
        "zp": AutoUnitKey("ExtZpos"),
    }

    def __init__(
        self,
        xn: float | str = None,
        xp: float | str = None,
        yn: float | str = None,
        yp: float | str = None,
        zn: float | str = None,
        zp: float | str = None,
    ):
        """
        Simple extent based stock

        :param xn: offset to X negative
        :param xp: offset to X positive
        :param yn: offset to Y negative
        :param yp: offset to Y positive
        :param zn: offset to Z negative
        :param zp: offset to Z positive
        """
        self.params = map_params(
            self._param_mapping,
            xn=xn,
            xp=xp,
            yn=yn,
            yp=yp,
            zn=zn,
            zp=zp,
        )
        self.fc_stock = None

    def create_stock(self, job_impl: JobImpl):
        fc_job = job_impl.fc_job
        job_impl.doc.removeObject(fc_job.Stock.Name)
        fc_stock = FCStock.CreateFromBase(job_impl.fc_job)
        apply_params(fc_stock, self.params, job_impl.units)
        PathUtil.setProperty(job_impl.fc_job, "Stock", fc_stock)
