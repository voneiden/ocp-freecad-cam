import sys

# This needs to be done due to some weird bug that causes
# ImportError: 'FreeCAD' is not a built-in module
# For example in CQ-Editor if import reload is enabled
if hasattr(sys, "_cached_freecad_module"):
    sys.modules["FreeCAD"] = sys._cached_freecad_module
else:
    import FreeCAD  # noqa

    sys._cached_freecad_module = sys.modules["FreeCAD"]

from ocp_freecad_cam.api import Job
from ocp_freecad_cam.api_tool import (
    Ballnose,
    Bullnose,
    Chamfer,
    Drill,
    Endmill,
    Probe,
    SlittingSaw,
    ThreadMill,
    VBit,
)

__all__ = [
    Job,
    Ballnose,
    Bullnose,
    Chamfer,
    Drill,
    Endmill,
    Probe,
    SlittingSaw,
    ThreadMill,
    VBit,
]
