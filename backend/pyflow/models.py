from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class PortSchema(BaseModel):
    name: str
    type: str
    required: bool = True
    default: Any = None


class NodeSchema(BaseModel):
    type: str
    label: str
    category: str = "General"
    description: str = ""
    inputs: list[PortSchema]
    outputs: list[PortSchema]
    kind: str = "function"


class GraphNode(BaseModel):
    id: str
    type: str
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0, "y": 0})
    params: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    source_handle: str = "result"
    target_handle: str


class SubflowDefinition(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    output_node: str
    output_handle: str = "result"


class GraphDefinition(BaseModel):
    id: str = "untitled"
    name: str = "Untitled pipeline"
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    subflows: dict[str, SubflowDefinition] = Field(default_factory=dict)


class NodeResult(BaseModel):
    value: Any = None
    outputs: dict[str, Any] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    metrics: dict[str, float | int | str] = Field(default_factory=dict)
    skipped_outputs: list[str] = Field(default_factory=list)
    child_runs: list[RunResult] = Field(default_factory=list)

    @classmethod
    def from_value(cls, value: Any, output_name: str = "result") -> "NodeResult":
        if isinstance(value, cls):
            return value
        return cls(value=value, outputs={output_name: value})


class NodeRun(BaseModel):
    node_id: str
    node_type: str
    status: Literal["pending", "running", "succeeded", "failed", "skipped"]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: NodeResult | None = None
    error: str | None = None
    skip_reason: Literal["branch", "upstream_error"] | None = None


class RunResult(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    status: Literal["succeeded", "failed"]
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime
    nodes: list[NodeRun]


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    order: list[str] = Field(default_factory=list)
