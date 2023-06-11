import io
from typing import TypeAlias, Union

import Path.Base.Util as PathUtil
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepTools import BRepTools
from OCP.gp import gp_Trsf
from OCP.TopAbs import TopAbs_EDGE, TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import (
    TopoDS_Builder,
    TopoDS_Compound,
    TopoDS_Edge,
    TopoDS_Face,
    TopoDS_Shape,
    TopoDS_Vertex,
    TopoDS_Wire,
)

try:
    import cadquery as cq
except ImportError:
    cq = None
try:
    import build123d as b3d
except ImportError:
    b3d = None

TopoDS_ShapeTypes: TypeAlias = Union[
    TopoDS_Face, TopoDS_Wire, TopoDS_Edge, TopoDS_Vertex, TopoDS_Compound
]
CompoundSource: TypeAlias = Union[
    TopoDS_Compound, "cq.Compound", "b3d.Compound", "cq.Workplane", "b3d.ShapeList"
]
ShapeSource: TypeAlias = Union[
    TopoDS_ShapeTypes,
    "cq.Workplane",
    "cq.Face",
    "cq.Wire",
    "cq.Edge",
    "cq.Vertex",
    "cq.Compound",
    "b3d.ShapeList",
    "b3d.Face",
    "b3d.Wire",
    "b3d.Edge",
    "b3d.Vertex",
    "b3d.Compound",
]
ShapeSourceOrIterable: TypeAlias = Union[ShapeSource, list[ShapeSource]]


# todo wire needs to be broken to edges..


def extract_topods_shapes(
    shape_source: ShapeSourceOrIterable, compound=False
) -> list[TopoDS_ShapeTypes]:
    if isinstance(shape_source, list):
        shapes = []
        for source in shape_source:
            shapes += extract_topods_shapes(source)
        return shapes

    if cq:
        valid_cq_shapes = (
            [cq.Compound] if compound else [cq.Face, cq.Wire, cq.Edge, cq.Vertex]
        )
        if isinstance(shape_source, cq.Workplane):
            return [
                shape.wrapped
                for shape in shape_source.objects
                if type(shape) in valid_cq_shapes
            ]
        elif type(shape_source) in valid_cq_shapes:
            return [shape_source.wrapped]
    if b3d:
        valid_b3d_shapes = (
            [b3d.Compound] if compound else [b3d.Face, b3d.Wire, b3d.Vertex]
        )
        if isinstance(shape_source, b3d.ShapeList):
            return [
                shape.wrapped
                for shape in shape_source
                if type(shape) in valid_b3d_shapes
            ]
        elif type(shape_source) in valid_b3d_shapes:
            return [shape_source.wrapped]

    valid_topods_shapes = (
        [TopoDS_Compound]
        if compound
        else [TopoDS_Face, TopoDS_Wire, TopoDS_Edge, TopoDS_Vertex]
    )
    if type(shape_source) in valid_topods_shapes:
        return [shape_source]

    raise ValueError(f"Unknown shape source of type {type(shape_source)}")


def split_shapes_by_type(
    shapes: list[TopoDS_ShapeTypes],
) -> tuple[list[TopoDS_Face], list[TopoDS_Edge], list[TopoDS_Vertex]]:
    faces = []
    wires = []
    edges = []
    vertices = []
    for shape in shapes:
        if isinstance(shape, TopoDS_Face):
            faces.append(shape)
        elif isinstance(shape, TopoDS_Wire):
            wires.append(shape)
        elif isinstance(shape, TopoDS_Edge):
            edges.append(shape)
        elif isinstance(shape, TopoDS_Vertex):
            vertices.append(shape)
        else:
            raise ValueError(f"Unknown shape type {type(shape)}")

    # Selecting wires is not supported by FreeCAD so explode wires
    # into edges
    for wire in wires:
        wire_edges = break_shape_to(wire, TopAbs_EDGE)
        edges += wire_edges

    return faces, edges, vertices


def break_shape_to(
    shape: TopoDS_Shape, shape_type: TopAbs_ShapeEnum
) -> list[TopoDS_Shape]:
    sub_shapes = []
    explorer = TopExp_Explorer(shape, shape_type)
    while explorer.More():
        sub_shape = explorer.Current()
        sub_shapes.append(sub_shape)
        explorer.Next()
    return sub_shapes


def transform_shapes(shapes: list[TopoDS_Shape], trsf: gp_Trsf) -> list[TopoDS_Shape]:
    return [transform_shape(shape, trsf) for shape in shapes]


def transform_shape(shape: TopoDS_Shape, trsf: gp_Trsf) -> TopoDS_Shape:
    return BRepBuilderAPI_Transform(shape, trsf).Shape()


def shapes_to_brep(shapes: list[TopoDS_Shape]):
    return [shape_to_brep(shape) for shape in shapes]


def shape_to_brep(shape: TopoDS_Shape):
    data = io.BytesIO()
    BRepTools.Write_s(shape, data)
    data.seek(0)
    return data.read().decode("utf8")


def shape_source_to_compound_brep(shape_source: ShapeSourceOrIterable, trsf: gp_Trsf):
    shapes = extract_topods_shapes(shape_source)
    faces, edges, vertices = split_shapes_by_type(shapes)

    if not faces and not edges and not vertices:
        raise ValueError("Empty ShapeSource")

    compound = TopoDS_Compound()
    builder = TopoDS_Builder()
    builder.MakeCompound(compound)

    for face in faces:
        builder.Add(compound, face)

    for edge in edges:
        builder.Add(compound, edge)

    for vertex in vertices:
        builder.Add(compound, vertex)

    return {
        "face_count": len(faces),
        "edge_count": len(edges),
        "vertex_count": len(vertices),
        "compound_brep": shape_to_brep(transform_shape(compound, trsf)),
    }


def clean_props(**kwargs):
    return {k: v for k, v in kwargs.items() if v is not None}


def map_prop(mapping, k, v):
    match mapping[k]:
        case (nk, dv):
            return nk, dv[v]
        case nk:
            return nk, v


def map_params(mapping: dict[str, Union[str, dict[str, str]]], **kwargs):
    return dict(map_prop(mapping, k, v) for k, v in kwargs.items() if v is not None)


def apply_params(fc_obj, params):
    for k, v in params.items():
        PathUtil.setProperty(fc_obj, k, v)
