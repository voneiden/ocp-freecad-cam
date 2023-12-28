from build123d import Axis, Box, Pos, offset

from ocp_freecad_cam import Endmill, Job

box = Box(10, 10, 5)
top = (box.faces() < Axis.Z)[0]
box -= Pos(0, 0, 1.5) * (
        Box(8, 8, 2) + Box(10, 2, 2)
)

op_faces = (box.faces() | Axis.Z < Axis.Z)[2]
op_faces = (
        offset(op_faces, 1)
        - box + op_faces
).faces()

tool = Endmill(diameter=1)
job = Job(top, box).pocket(op_faces, tool=tool, pattern="offset")
