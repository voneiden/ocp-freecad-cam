from OCP.gp import gp_Ax3, gp_Pln, gp_Trsf


def calculate_transforms(plane: gp_Pln) -> (gp_Trsf, gp_Trsf):
    """
    Implementation from CadQuery

    Forward transform relative to top plane everything that goes to FreeCAD
    Backward transform to visualize stuff produced by FreeCAD

    """
    forward = gp_Trsf()
    backward = gp_Trsf()

    global_coord_system = gp_Ax3()
    local_coord_system = plane.Position()

    forward.SetTransformation(global_coord_system, local_coord_system)
    backward.SetTransformation(local_coord_system, global_coord_system)

    return forward, backward
