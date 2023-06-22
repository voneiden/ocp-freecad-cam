from build123d import Axis, Box, BuildPart

from ocp_freecad_cam import Endmill, Job

with BuildPart() as part:
    Box(5, 5, 2)

z_faces = part.faces().sort_by(Axis.Z)
top = z_faces[-1]
bottom = z_faces[0]

tool = Endmill(diameter=1)
job = Job(top, part.solids()).profile(bottom, tool)
