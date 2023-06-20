from dataclasses import dataclass, field
from typing import ClassVar, Literal, Optional

from Path.Tool import Bit, Controller

from ocp_freecad_cam.api_util import AutoUnitKey, ParamMapping, apply_params, map_params


class FCBit:
    ...
    Proxy: Bit.ToolBit


class FCToolController:
    ...
    Proxy: Controller.ToolController


@dataclass(kw_only=True)
class Toolbit:
    _bit: Optional[FCBit] = field(init=False)
    _tool_controller: Optional[FCToolController] = field(init=False)
    params: dict[str, str] = field(init=False)
    param_mapping: ClassVar[ParamMapping] = {
        "chip_load": "ChipLoad",
        "flutes": "Flutes",
        "material": "Material",
    }

    tc_param_mapping: ClassVar[ParamMapping] = {
        "spindle_dir": (
            "SpindleDirection",
            {"forward": "Forward", "reverse": "Reverse", "none": "None"},
        ),
        "h_feed": AutoUnitKey("HorizFeed", mode="feed"),
        "v_feed": AutoUnitKey("VertFeed", mode="feed"),
    }

    _file_name: ClassVar[str]

    name: str = ""
    number: int = 1
    path: Optional[str] = None

    chip_load: str = None
    flutes: int = None
    material: str = None

    # TC attributes
    h_feed: float | str = None
    v_feed: float | str = None
    spindle_dir: Literal["forward", "reverse", "none"] = None

    def __post_init__(self):
        self._bit = None
        self._tool_controller = None

        self.params = map_params(
            self.param_mapping, **self._collect_params(self.param_mapping)
        )
        self.tc_params = map_params(
            self.tc_param_mapping, **self._collect_params(self.tc_param_mapping)
        )

    def _collect_params(self, mapping: ParamMapping):
        return {k: v for k in mapping.keys() if (v := getattr(self, k)) is not None}

    def tool_controller(self, fc_job, units):
        if self._tool_controller is None:
            self.create(fc_job, units)
        return self._tool_controller

    def create(self, fc_job, units):
        tool_shape = Bit.findToolShape(self._file_name, self.path)
        if not tool_shape:
            raise ValueError(
                f"Could not find tool {self._file_name} (path: {self.path})"
            )

        self._bit = Bit.Factory.Create(self.name, tool_shape)
        self._tool_controller = Controller.Create(
            f"TC: {self.name}", tool=self._bit, toolNumber=self.number
        )
        fc_job.addToolController(self._tool_controller)
        apply_params(self._bit, self.params, units)
        apply_params(self._tool_controller, self.tc_params, units)


@dataclass(kw_only=True)
class Endmill(Toolbit):
    _file_name: ClassVar[str] = "endmill.fcstd"
    param_mapping = {
        **Toolbit.param_mapping,
        "cutting_edge_height": AutoUnitKey("CuttingEdgeHeight"),
        "diameter": AutoUnitKey("Diameter"),
        "length": AutoUnitKey("Length"),
        "shank_diameter": AutoUnitKey("Shank Diameter"),
    }

    cutting_edge_height: float | str = None
    diameter: float | str = None
    length: float | str = None
    shank_diameter: float | str = None


@dataclass(kw_only=True)
class Ballnose(Endmill):
    _file_name: ClassVar[str] = "ballnose.fcstd"


@dataclass(kw_only=True)
class VBit(Endmill):
    _file_name: ClassVar[str] = "v-bit.fcstd"

    param_mapping = {
        **Endmill.param_mapping,
        "tip_angle": "TipAngle",
        "tip_diameter": AutoUnitKey("TipDiameter"),
    }

    tip_angle: float = None
    tip_diameter: float | str = None


@dataclass(kw_only=True)
class Chamfer(VBit):
    _file_name: ClassVar[str] = "chamfer.fcstd"


@dataclass(kw_only=True)
class Drill(Toolbit):
    _file_name: ClassVar[str] = "drill.fcstd"
    param_mapping = {
        **Toolbit.param_mapping,
        "diameter": AutoUnitKey("Diameter"),
        "length": AutoUnitKey("Length"),
        "tip_angle": AutoUnitKey("TipAngle"),
    }

    diameter: float | str = None
    length: float | str = None
    tip_angle: float = None


@dataclass(kw_only=True)
class Probe(Toolbit):
    _file_name: ClassVar[str] = "probe.fcstd"
    param_mapping = {
        **Toolbit.param_mapping,
        "diameter": AutoUnitKey("Diameter"),
        "length": AutoUnitKey("Length"),
        "shank_diameter": AutoUnitKey("Shank Diameter"),
    }

    diameter: float | str = None
    length: float | str = None
    shank_diameter: float | str = None


@dataclass(kw_only=True)
class SlittingSaw(Toolbit):
    _file_name: ClassVar[str] = "slittingsaw.fcstd"
    param_mapping = {
        **Toolbit.param_mapping,
        "blade_thickness": AutoUnitKey("BladeThickness"),
        "cap_diameter": AutoUnitKey("CapDiameter"),
        "cap_height": AutoUnitKey("CapHeight"),
        "diameter": AutoUnitKey("Diameter"),
        "length": AutoUnitKey("Length"),
        "shank_diameter": AutoUnitKey("Shank Diameter"),
    }

    blade_thickness: float | str = None
    cap_diameter: float | str = None
    cap_height: float | str = None
    diameter: float | str = None
    length: float | str = None
    shank_diameter: float | str = None


@dataclass(kw_only=True)
class Bullnose(Endmill):
    _file_name: ClassVar[str] = "bullnose.fcstd"
    param_mapping = {
        **Endmill.param_mapping,
        "flat_radius": AutoUnitKey("FlatRadius"),
    }
    flat_radius: float | str = None


@dataclass(kw_only=True)
class ThreadMill(Toolbit):
    _file_name: ClassVar[str] = "bullnose.fcstd"
    param_mapping = {
        **Toolbit.param_mapping,
        "crest": AutoUnitKey("Crest"),
        "diameter": AutoUnitKey("Diameter"),
        "length": AutoUnitKey("Length"),
        "neck_diameter": AutoUnitKey("NeckDiameter"),
        "neck_length": AutoUnitKey("NeckLength"),
        "shank_diameter": AutoUnitKey("ShankDiameter"),
        "cutting_angle": "cuttingAngle",
    }

    crest: float | str = None
    diameter: float | str = None
    length: float | str = None
    neck_diameter: float | str = None
    neck_length: float | str = None
    shank_diameter: float | str = None
    cutting_angle: float = None
