from abc import ABC
from itertools import pairwise

from OCP.AIS import AIS_MultipleConnectedInteractive, AIS_Line
from OCP.Geom import Geom_CartesianPoint
from OCP.gp import gp_Trsf, gp_Vec
from Path.Main import Job as FC_Job
from Path.Base.MachineState import MachineState


class VisualCommand(ABC):
    def __init__(self, *, x, y, z, **kwargs):
        self.x = x
        self.y = y
        self.z = z

    def to_ais(self, start: 'VisualCommand'):
        raise NotImplemented

    def __eq__(self, other):
        if isinstance(other, VisualCommand):
            return self.x == other.x and self.y == other.y and self.z == other.z
        raise TypeError(f"Can not compare {type(self)} with {type(other)}")


class LinearVisualCommand(VisualCommand):
    def to_ais(self, start: 'VisualCommand'):
        if start == self:
            return None
        start_point = Geom_CartesianPoint(start.x, start.y, start.z)
        end_point = Geom_CartesianPoint(self.x, self.y, self.z)
        # todo empty lines
        return AIS_Line(start_point, end_point)

class RapidVisualCommand(LinearVisualCommand):
    pass


class ArcVisualCommand(LinearVisualCommand):
    def __init__(self, *, i, j, k, **kwargs):
        super().__init__(**kwargs)

        self.i = i
        self.j = j
        self.k = k

class CWArcVisualCommand(ArcVisualCommand):
    pass


class CCWArcVisualCommand(ArcVisualCommand):
    pass



def visualize_fc_job(job: FC_Job.ObjectJob, inverse_trsf: gp_Trsf):
    """
    Visualize a FreeCAD job
    https://wiki.freecad.org/Path_scripting#The_FreeCAD_Internal_GCode_Format
    """
    params = {}
    relative = False

    visual_commands = []

    for op in job.allOperations():
        for command in op.Proxy.commandlist:
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
            print("CP", command.Name, combined_params)
            match command.Name:
                case "G0":
                    params = add_command(visual_commands, RapidVisualCommand, **combined_params)
                case "G1":
                    params = add_command(visual_commands, LinearVisualCommand, **combined_params)
                case "G2":
                    params = add_command(visual_commands, CWArcVisualCommand, **combined_params)
                case "G3":
                    params = add_command(visual_commands, CCWArcVisualCommand, **combined_params)

                case "G91":
                    relative = True
                    print("Relative mode on")
                case "G90":
                    relative = False
                    print("Relative mode off")

                case _:
                    print("Unknown gcode", command.Name)

            #print(command.Name, command.Parameters)
            # print(dir(command))
        #print(op.Proxy.commandlist)
        #print(visual_commands)
        if len(visual_commands) < 2:
            return

        group = AIS_MultipleConnectedInteractive()
        # Adjust for stock
        #tp = inverse_trsf.TranslationPart()
        #tp.SetZ(tp.Z() - 1)
        #inverse_trsf.SetTranslationPart(gp_Vec(tp))
        group.SetLocalTransformation(inverse_trsf)

        for start, end in pairwise(visual_commands):
            shape = end.to_ais(start)
            if shape:
                group.Connect(shape)
        return group

def add_command(visual_commands: list[VisualCommand], cls: type[VisualCommand], **params):
    try:
        cmd = cls(**params)
        visual_commands.append(cmd)
    except TypeError:
        print(" Bonk")
    return params