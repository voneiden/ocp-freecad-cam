from OCP.AIS import AIS_DisplayMode, AIS_InteractiveContext, AIS_Shaded, AIS_Shape
from OCP.Aspect import Aspect_DisplayConnection, Aspect_TypeOfTriedronPosition
from OCP.Image import Image_AlienPixMap
from OCP.OpenGl import OpenGl_GraphicDriver
from OCP.Quantity import Quantity_Color
from OCP.TCollection import TCollection_AsciiString
from OCP.V3d import V3d_Viewer
from OCP.Xw import Xw_Window

from ocp_freecad_cam.api import Job
from ocp_freecad_cam.api_util import extract_topods_shapes


def render(shapes, output_path):
    display_connection = Aspect_DisplayConnection()
    graphic_driver = OpenGl_GraphicDriver(display_connection)
    viewer = V3d_Viewer(graphic_driver)
    viewer.SetDefaultLights()
    viewer.SetLightOn()

    context = AIS_InteractiveContext(viewer)
    context.SetDisplayMode(AIS_DisplayMode.AIS_Shaded, True)
    context.DefaultDrawer().SetFaceBoundaryDraw(True)
    view = viewer.CreateView()
    view.TriedronDisplay(
        Aspect_TypeOfTriedronPosition.Aspect_TOTP_RIGHT_LOWER, Quantity_Color(), 0.1
    )
    params = view.ChangeRenderingParams()
    params.NbMsaaSamples = 8
    params.IsAntialiasingEnabled = True
    window = Xw_Window(display_connection, "", 0, 0, 660, 495)
    window.SetVirtual(True)
    view.SetWindow(window)
    view.MustBeResized()

    for shape in shapes:
        context.Display(shape, False)

    view.FitAll()
    view.Redraw()

    image = Image_AlienPixMap()
    view.ToPixMap(image, 660, 495)
    image.Save(TCollection_AsciiString(output_path))


def render_file(file_path, display_object_names, output_path):
    with open(file_path, "r") as f:
        ast = compile(f.read(), file_path, "exec")

    _locals = {}
    exec(ast, _locals)

    display_shapes = []
    for name in display_object_names:
        obj = _locals[name]
        if isinstance(obj, Job):
            display_shapes.append(obj.show())
        else:
            shapes = extract_topods_shapes(obj)
            if not shapes:
                shapes = extract_topods_shapes(obj, compound=True)
            if not shapes:
                raise ValueError("No shapes found)")
            ais_shapes = []
            for shape in shapes:
                ais_shape = AIS_Shape(shape)
                ais_shape.SetHilightMode(AIS_Shaded)
                ais_shapes.append(ais_shape)

            display_shapes += ais_shapes

    render(display_shapes, output_path)


if __name__ == "__main__":
    render_file("cq_profile.py", ["wp", "job"], "images/cq_profile.png")
    render_file("cq_pocket.py", ["wp", "job"], "images/cq_pocket.png")
    render_file("cq_drill.py", ["wp", "job"], "images/cq_drill.png")
    render_file("cq_helix.py", ["wp", "job"], "images/cq_helix.png")
    render_file("cq_adaptive.py", ["wp", "job"], "images/cq_adaptive.png")
