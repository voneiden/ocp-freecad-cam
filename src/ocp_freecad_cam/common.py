from typing import TYPE_CHECKING, Literal, TypeAlias, Union

if TYPE_CHECKING:
    import build123d as b3d
    import cadquery as cq

FaceSource: TypeAlias = Union[
    "cq.Workplane", "cq.Face", list["cq.Face"], "b3d.Face", list["b3d.Face"]
]
PlaneSource: TypeAlias = Union[
    "cq.Workplane", "cq.Plane", "cq.Face", "b3d.Plane", "b3d.Face"
]
Plane: TypeAlias = Union["cq.Plane", "b3d.Plane"]


PostProcessor: TypeAlias = Literal[
    "KineticNCBeamicon2",
    "centroid",
    "comparams",
    "dxf",
    "dynapath",
    "fablin",
    "fangling",
    "fanuc",
    "grbl",
    "heidenhain",
    "jtech",
    "linuxcnc",
    "mach3_mach4",
    "marlin",
    "nccad",
    "opensbp",
    "philips",
    "refactored_centroid",
    "refactored_grbl",
    "refactored_linuxcnc",
    "refactored_mach3_mach4",
    "refactored_test",
    "rml",
    "rrf",
    "smoothie",
    "uccnc",
]
