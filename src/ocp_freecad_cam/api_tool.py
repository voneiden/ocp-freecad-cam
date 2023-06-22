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
    """
    Base class for Toolbits
    """

    _bit: Optional[FCBit] = field(init=False)
    _tool_controller: Optional[FCToolController] = field(init=False)
    params: dict[str, str] = field(init=False)
    param_mapping: ClassVar[ParamMapping] = {
        # "chip_load": "ChipLoad",
        # "flutes": "Flutes",
        # "material": "Material",
    }

    tc_param_mapping: ClassVar[ParamMapping] = {
        "speed": "SpindleSpeed",
        "spindle_dir": (
            "SpindleDirection",
            {"forward": "Forward", "reverse": "Reverse", "none": "None"},
        ),
        "h_feed": AutoUnitKey("HorizFeed", mode="feed"),
        "v_feed": AutoUnitKey("VertFeed", mode="feed"),
    }

    _file_name: ClassVar[str]

    name: str = ""
    """ Completely optional tool name """

    number: int = 1
    """ Tool number for tool change purposes """

    path: Optional[str] = None
    """ 
    Tool shape path. Not needed if the shape is located in the expected
    library folder 
    """

    # Removed these three attributes as they have currently
    # no function in FreeCAD besides bookkeeping.
    # chip_load: str = None
    # flutes: int = None
    # material: str = None

    # TC attributes
    h_feed: float | str = None
    """
    Horizontal feed rate. Units are either mm/min or in/min. Floats
    are interpreted with the job units. Strings should include the unit.
    """
    v_feed: float | str = None
    """
    Vertical feed rate. Units are either mm/min or in/min. Floats
    are interpreted with the job units. Strings should include the unit.
    """
    speed: float | str = None
    """
    Spindle speed in RPM.
    """
    spindle_dir: Literal["forward", "reverse", "none"] = None
    """
    Spindle direction, forward (clockwise) or reverse (counterclockwise).
    """

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
    """
    Endmill is the standard cylindrical tool bit.
    """

    _file_name: ClassVar[str] = "endmill.fcstd"
    param_mapping = {
        **Toolbit.param_mapping,
        "cutting_edge_height": AutoUnitKey("CuttingEdgeHeight"),
        "diameter": AutoUnitKey("Diameter"),
        "length": AutoUnitKey("Length"),
        "shank_diameter": AutoUnitKey("Shank Diameter"),
    }

    cutting_edge_height: float | str = None
    """ 
    Length of the cutter aka maximum cut depth. Floats are interpreted 
    either in mm or in depending on job unit.
    """
    diameter: float | str = None
    """ 
    Diameter of the cutter. Floats are interpreted 
    either in mm or in depending on job unit.
    """
    length: float | str = None
    """ 
    Total length of the tool from spindle holder. Floats are interpreted 
    either in mm or in depending on job unit.
    """
    shank_diameter: float | str = None
    """ 
    Diameter of the shank abover the cutter. Floats are interpreted 
    either in mm or in depending on job unit.
    """


@dataclass(kw_only=True)
class Ballnose(Endmill):
    """
    Ballnose is an Endmill with a round tip.
    """

    _file_name: ClassVar[str] = "ballnose.fcstd"


@dataclass(kw_only=True)
class VBit(Endmill):
    """
    V-Bit's are engraving tools that come in various shapes. Depth of cut
    defines the cut width. Typically used with the V-Carve operation (for
    variable width cuts) or Engrave operation (for constant width).
    """

    _file_name: ClassVar[str] = "v-bit.fcstd"

    param_mapping = {
        **Endmill.param_mapping,
        "tip_angle": "TipAngle",
        "tip_diameter": AutoUnitKey("TipDiameter"),
    }

    tip_angle: float = None
    """ Tip angle in degrees, typically 15, 30, 60 or 90. """
    tip_diameter: float | str = None
    """ 
    Diameter of the tip. Friendly reminder that low grade V-bits have
    huge disparity, ie something advertised as 0.1 mm can be actually 0.3 m.
    Measure your bits if doing high detail work!
    
    Floats are interpreted either in mm or in depending on Job unit.
    """


@dataclass(kw_only=True)
class Chamfer(VBit):
    """
    Chamfer has same attributes as a VBit. In practice, they have usually
    comparatively wide tip diameters.
    """

    _file_name: ClassVar[str] = "chamfer.fcstd"


@dataclass(kw_only=True)
class Drill(Toolbit):
    """
    A Drill tool for.. drilling holes!
    """

    _file_name: ClassVar[str] = "drill.fcstd"
    param_mapping = {
        **Toolbit.param_mapping,
        "diameter": AutoUnitKey("Diameter"),
        "length": AutoUnitKey("Length"),
        "tip_angle": AutoUnitKey("TipAngle"),
    }

    diameter: float | str = None
    """ 
    Diameter of the drill. Floats are interpreted either in mm or in 
    depending on job unit. 
    """
    length: float | str = None
    """
    Length of the drill from tip to collet. Floats are interpreted either 
    in mm or in depending on job unit. 
    """
    tip_angle: float = None
    """
    Tip angle in degrees. Determines the extra distance of penetration needed
    to get the correct hole size.
    """


@dataclass(kw_only=True)
class Probe(Toolbit):
    """
    Please refer to FreeCAD on how to use this tool.
    """

    _file_name: ClassVar[str] = "probe.fcstd"
    param_mapping = {
        **Toolbit.param_mapping,
        "diameter": AutoUnitKey("Diameter"),
        "length": AutoUnitKey("Length"),
        "shank_diameter": AutoUnitKey("Shank Diameter"),
    }

    diameter: float | str = None
    """ 
    Diameter of the probe. Floats are interpreted either in mm or in 
    depending on job unit. 
    """
    length: float | str = None
    """
    Length of the drill from tip to collet. Floats are interpreted either 
    in mm or in depending on job unit. 
    """
    shank_diameter: float | str = None
    """ 
    Diameter of the probe shank. Probably irrelevant in FreeCAD. 
    Floats are interpreted either in mm or in depending on job unit. 
    """


@dataclass(kw_only=True)
class SlittingSaw(Toolbit):
    """
    Please refer to FreeCAD on how to use this.
    """

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
    """
    A mix of Endmill and Ballnose, the Bullnose has a flat area
    at the tip with rounded cutting edges.
    """

    _file_name: ClassVar[str] = "bullnose.fcstd"
    param_mapping = {
        **Endmill.param_mapping,
        "flat_radius": AutoUnitKey("FlatRadius"),
    }
    flat_radius: float | str = None
    """
    The radius of the flat part and the tip of the tool.
    Floats are interpreted either in mm or in depending on job unit. 
    """


@dataclass(kw_only=True)
class ThreadMill(Toolbit):
    """
    Please refer to FreeCAD on how to use this tool.
    """

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
