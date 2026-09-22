from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Union, get_args, get_origin, get_type_hints
from types import UnionType
from pydantic import TypeAdapter

from .models import NodeResult, NodeSchema, PortSchema


def _type_name(annotation: Any) -> str:
    if annotation is inspect.Parameter.empty or annotation is Any:
        return "any"
    origin = get_origin(annotation)
    if origin:
        args = ", ".join(_type_name(arg) for arg in get_args(annotation))
        return f"{getattr(origin, '__name__', str(origin))}[{args}]"
    return getattr(annotation, "__name__", str(annotation).replace("typing.", ""))


@dataclass(slots=True)
class RegisteredNode:
    schema: NodeSchema
    function: Callable[..., Any]
    input_types: dict[str, Any]
    output_types: dict[str, Any]


class NodeRegistry:
    def __init__(self) -> None:
        self._nodes: dict[str, RegisteredNode] = {}

    def register(
        self,
        function: Callable[..., Any],
        *,
        name: str | None = None,
        label: str | None = None,
        category: str = "General",
        description: str = "",
        outputs: dict[str, Any] | None = None,
        kind: str = "function",
    ) -> Callable[..., Any]:
        node_type = name or function.__name__
        if kind not in ("function", "merge", "subflow", "map_subflow"):
            raise ValueError("Unknown execution kind")
        if node_type in self._nodes:
            raise ValueError(f"Duplicate node type: {node_type}")
        signature = inspect.signature(function)
        hints = get_type_hints(function)
        input_types = {}
        inputs = []
        for param in signature.parameters.values():
            if param.kind not in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY):
                raise ValueError("Only named parameters are supported")
            annotation = hints.get(param.name, Any)
            input_types[param.name] = annotation
            required = param.default is inspect.Parameter.empty
            if not required:
                TypeAdapter(annotation).validate_python(param.default, strict=True)
            inputs.append(PortSchema(
                name=param.name,
                type=_type_name(annotation),
                required=required,
                default=None if required else param.default,
            ))
        result_type = hints.get("return", Any)
        output_types = outputs or {"result": Any if result_type is NodeResult else result_type}
        output_ports = [PortSchema(name=k, type=_type_name(v)) for k, v in output_types.items()]
        schema = NodeSchema(
            type=node_type,
            label=label or node_type.replace("_", " ").title(),
            category=category,
            description=description or (inspect.getdoc(function) or ""),
            inputs=inputs,
            outputs=output_ports,
            kind=kind,
        )
        schema.model_dump_json()
        self._nodes[node_type] = RegisteredNode(schema, function, input_types, output_types)
        return function

    def get(self, node_type: str) -> RegisteredNode:
        try:
            return self._nodes[node_type]
        except KeyError as exc:
            raise KeyError(f"Unknown node type: {node_type}") from exc

    def catalog(self) -> list[NodeSchema]:
        return [item.schema for item in self._nodes.values()]


registry = NodeRegistry()


def compatible(source: Any, target: Any) -> bool:
    if source is Any or target is Any or source == target:
        return True
    so, to = get_origin(source), get_origin(target)
    if so in (Union, UnionType):
        return all(compatible(part, target) for part in get_args(source))
    if to in (Union, UnionType):
        return any(compatible(source, part) for part in get_args(target))
    if (so or source) != (to or target):
        return source is int and target is float
    sa, ta = get_args(source), get_args(target)
    return not ta or (len(sa) == len(ta) and all(compatible(s, t) for s, t in zip(sa, ta)))


def node(
    function: Callable[..., Any] | None = None,
    **metadata: Any,
) -> Callable[..., Any]:
    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        registry.register(fn, **metadata)
        return fn

    return decorate(function) if function else decorate
