from __future__ import annotations

import asyncio
import re
from typing import Any

from .models import NodeResult
from .registry import node
from .batch import split_value, join_value


@node(category="Input", description="Provide text to the pipeline")
def text_input(text: str = "Paste a document here") -> str:
    return text


@node(category="Text", description="Normalize whitespace while preserving paragraphs", outputs={"result": str})
def normalize_text(text: str) -> NodeResult:
    paragraphs = [re.sub(r"\s+", " ", part).strip() for part in text.split("\n\n")]
    normalized = "\n\n".join(part for part in paragraphs if part)
    return NodeResult(
        value=normalized,
        outputs={"result": normalized},
        logs=[f"Normalized {len(text)} characters to {len(normalized)}"],
        metrics={"input_chars": len(text), "output_chars": len(normalized)},
    )


@node(category="Text", description="Split text into overlapping character chunks", outputs={"result": list[str]})
def chunk_text(text: str, size: int = 400, overlap: int = 40) -> NodeResult:
    if size < 1:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be between 0 and size - 1")
    step = size - overlap
    chunks = []
    for index in range(0, len(text), step):
        chunks.append(text[index:index + size])
        if index + size >= len(text):
            break
    return NodeResult(
        value=chunks,
        outputs={"result": chunks},
        logs=[f"Created {len(chunks)} chunks"],
        metrics={"chunk_count": len(chunks), "size": size, "overlap": overlap},
    )


@node(category="Transform", description="Count items or characters")
def count(value: Any) -> int:
    return len(value)


@node(category="Control", description="Wait to simulate an asynchronous service")
async def delay(value: Any, milliseconds: int = 100) -> NodeResult:
    if milliseconds < 0:
        raise ValueError("milliseconds must be nonnegative")
    await asyncio.sleep(milliseconds / 1000)
    return NodeResult(
        value=value,
        outputs={"result": value},
        logs=[f"Waited {milliseconds} ms"],
        metrics={"delay_ms": milliseconds},
    )


@node(category="Output", description="Return a value and attach a label")
def preview(value: Any, label: str = "Output") -> NodeResult:
    return NodeResult(
        value=value,
        outputs={"result": value},
        logs=[f"{label} is ready for preview"],
    )


@node(category="Input", description="Inject a JSON value when the flow is run")
def inject(value: Any = None) -> Any:
    return value


@node(category="Control", description="Route a value to true or false; inactive branch is skipped", outputs={"true": Any, "false": Any})
def switch(value: Any, operator: str = "equals", expected: Any = None) -> NodeResult:
    if operator == "equals":
        passed = value == expected
    elif operator == "contains":
        passed = expected in value
    elif operator == "greater":
        passed = value > expected
    elif operator == "truthy":
        passed = bool(value)
    else:
        raise ValueError("operator must be equals, contains, greater, or truthy")
    active, inactive = ("true", "false") if passed else ("false", "true")
    return NodeResult(value=value, outputs={active: value}, skipped_outputs=[inactive], logs=[f"Route: {active}"])


@node(category="Transform", description="Extract a nested JSON value with a dot path, e.g. user.name")
def select_field(value: Any, path: str = "") -> Any:
    for part in path.split(".") if path else []:
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


@node(category="Transform", description="Set one top-level field in a JSON object")
def change(value: dict, key: str, replacement: Any = None) -> dict:
    return {**value, key: replacement}


@node(category="Output", description="Inspect the exact incoming JSON value and pass it through")
def debug(value: Any, label: str = "Debug") -> NodeResult:
    return NodeResult(value=value, outputs={"result": value}, logs=[f"{label}: captured output"])


@node(category="Control", kind="merge", description="Merge active branches; first uses left-before-right order, all returns a list")
def merge(left: Any = None, right: Any = None, mode: str = "first") -> Any:
    # The executor supplies only active branches, preserving an active null.
    raise RuntimeError("Merge requires the graph executor")


@node(category="Batch", description="Split a list or delimited text into indexed batch items (max 1000)")
def split(value: Any, separator: str = "\n") -> dict:
    return split_value(value, separator)


@node(category="Batch", description="Join a complete batch by original index; preserves list or text format")
def join(value: dict) -> Any:
    return join_value(value)


@node(category="Subflow", description="The single external input of a reusable subflow")
def subflow_input(value: Any = None) -> Any:
    return value


@node(category="Subflow", kind="subflow", description="Run a named reusable graph with one input and one output")
def subflow(value: Any, flow: str) -> Any:
    raise RuntimeError("Subflow requires the graph executor")


@node(category="Batch", kind="map_subflow", description="Apply a named subflow to each batch item, preserving its index")
def map_subflow(value: dict, flow: str) -> dict:
    raise RuntimeError("Map subflow requires the graph executor")
