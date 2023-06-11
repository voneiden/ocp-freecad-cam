import math
import typing
from abc import ABC
from itertools import pairwise
from typing import Optional

from OCP.AIS import AIS_Circle, AIS_Line, AIS_MultipleConnectedInteractive
from OCP.Geom import Geom_CartesianPoint, Geom_Circle
from OCP.GeomAPI import GeomAPI_ProjectPointOnCurve
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from Path.Post.Command import buildPostList

if typing.TYPE_CHECKING:
    from Path.Main import Job as FC_Job


class VisualCommand(ABC):
    def __init__(self, *, x, y, z, **kwargs):
        self.x = x
        self.y = y
        self.z = z

    def to_ais(self, start: "VisualCommand"):
        raise NotImplemented

    def __eq__(self, other):
        if isinstance(other, VisualCommand):
            return self.x == other.x and self.y == other.y and self.z == other.z
        raise TypeError(f"Can not compare {type(self)} with {type(other)}")


class LinearVisualCommand(VisualCommand):
    def to_ais(self, start: "VisualCommand"):
        if start == self:
            return None
        start_point = Geom_CartesianPoint(start.x, start.y, start.z)
        end_point = Geom_CartesianPoint(self.x, self.y, self.z)
        # todo empty lines
        return AIS_Line(start_point, end_point)


class RapidVisualCommand(LinearVisualCommand):
    pass


class ArcVisualCommand(LinearVisualCommand, ABC):
    def __init__(self, *, i, j, k, arc_plane, **kwargs):
        super().__init__(**kwargs)
        self.arc_plane = arc_plane
        self.i = i
        self.j = j
        self.k = k

    def circle_normal_dir(self, circle_normal: gp_Vec):
        raise NotImplemented

    def to_ais(self, start: VisualCommand):
        cx = start.x + self.i
        cy = start.y + self.j
        cz = start.z + self.k
        radius = math.sqrt(self.i**2 + self.j**2 + self.k**2)
        c = gp_Pnt(cx, cy, cz)
        # XY
        arc_plane = gp_Vec(*self.arc_plane)
        cv = gp_Vec(self.i, self.j, self.k)
        forward = cv.Crossed(arc_plane)
        circle_normal = cv.Crossed(forward)
        circle_normal_dir = self.circle_normal_dir(circle_normal)

        forward_dir = gp_Dir(forward.X(), forward.Y(), forward.Z())
        circle_ax = gp_Ax2(c, circle_normal_dir, forward_dir)
        geom_circle = Geom_Circle(circle_ax, radius)
        start_point = gp_Pnt(start.x, start.y, start.z)
        end_point = gp_Pnt(self.x, self.y, self.z)
        u_start = GeomAPI_ProjectPointOnCurve(
            start_point, geom_circle
        ).LowerDistanceParameter()
        u_end = GeomAPI_ProjectPointOnCurve(
            end_point, geom_circle
        ).LowerDistanceParameter()
        if u_end < u_start:
            u_start -= math.pi * 2
        return AIS_Circle(geom_circle, u_start, u_end)


class CWArcVisualCommand(ArcVisualCommand):
    def circle_normal_dir(self, circle_normal: gp_Vec):
        return gp_Dir(circle_normal.X(), circle_normal.Y(), circle_normal.Z())


class CCWArcVisualCommand(ArcVisualCommand):
    def circle_normal_dir(self, circle_normal: gp_Vec):
        return gp_Dir(-circle_normal.X(), -circle_normal.Y(), -circle_normal.Z())


def visualize_fc_job(job, inverse_trsf: gp_Trsf):
    """
    Visualize a FreeCAD job
    https://wiki.freecad.org/Path_scripting#The_FreeCAD_Internal_GCode_Format
    """
    params = {"arc_plane": (0, 0, 1)}
    relative = False
    canned = False
    canned_r = False
    canned_z = None

    visual_commands = []

    postlist = buildPostList(job)
    print("All ops", [o.Name for o in job.Proxy.allOperations()])
    for name, sub_op_list in postlist:
        for op in sub_op_list:
            if hasattr(op, "Path"):
                commands = op.Path.Commands
            else:
                commands = op.Proxy.commandlist

            for command in commands:
                new_params = {k.lower(): v for k, v in command.Parameters.items()}
                if relative:
                    # Convert to absolute
                    rel_attrs = ["x", "y", "z"]
                    for attr in rel_attrs:
                        if attr in new_params:
                            # This will catch fire if params does not have a previous value
                            # Not sure if FreeCAD generates code like that, so lets see
                            # if it needs to be handled..
                            new_params[attr] = new_params[attr] + params[attr]
                combined_params = {**params, **new_params}
                match command.Name:
                    case "G0":
                        params = add_command(
                            visual_commands, RapidVisualCommand, **combined_params
                        )
                    case "G1":
                        params = add_command(
                            visual_commands, LinearVisualCommand, **combined_params
                        )
                    case "G2":
                        params = add_command(
                            visual_commands, CWArcVisualCommand, **combined_params
                        )
                    case "G3":
                        params = add_command(
                            visual_commands, CCWArcVisualCommand, **combined_params
                        )
                    case "G17":
                        params["arc_plane"] = (0, 0, 1)
                    case "G18":
                        params["arc_plane"] = (0, 1, 0)
                    case "G19":
                        params["arc_plane"] = (1, 0, 0)
                    case "G81":
                        # Canned cycle
                        # FreeCAD canned cycle looks to be in a format like
                        # G81 X2.000 Y-2.000 Z-2.000 R3.000
                        # So we issue two commands, first going down to Z
                        # and then coming back up to R
                        if not canned:
                            if not canned_r:
                                canned_z = params["z"]
                            canned = True

                        add_command(
                            visual_commands, LinearVisualCommand, **combined_params
                        )
                        if canned_r:
                            combined_params = {
                                **combined_params,
                                "z": combined_params["r"],
                            }
                        else:
                            combined_params = {**combined_params, "z": canned_z}
                        params = add_command(
                            visual_commands, LinearVisualCommand, **combined_params
                        )

                    case "G80":
                        # End of canned cycle
                        canned = False

                    case "G91":
                        relative = True
                        print("Relative mode on")
                    case "G90":
                        relative = False
                        print("Relative mode off")

                    case "G98":
                        # Canned cycle mode, probably not relevant
                        canned_r = False
                    case "G99":
                        canned_r = True

                    case _:
                        if command.Name.startswith("("):
                            continue
                        print("Unknown gcode", command.Name)

    return visual_commands_to_ais(visual_commands, inverse_trsf=inverse_trsf)


def visual_commands_to_ais(
    visual_commands: list[VisualCommand], inverse_trsf: Optional[gp_Trsf] = None
):
    if len(visual_commands) < 2:
        return

    group = AIS_MultipleConnectedInteractive()

    if inverse_trsf:
        group.SetLocalTransformation(inverse_trsf)

    for start, end in pairwise(visual_commands):
        shape = end.to_ais(start)
        if shape:
            group.Connect(shape)

    return group


def add_command(
    visual_commands: list[VisualCommand], cls: type[VisualCommand], **params
):
    try:
        cmd = cls(**params)
        visual_commands.append(cmd)
    except TypeError:
        print(" Bonk")
    return params
