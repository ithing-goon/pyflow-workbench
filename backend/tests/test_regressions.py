from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pyflow.api import app
from pyflow.executor import GraphExecutor
from pyflow.models import GraphDefinition, NodeResult
from pyflow.nodes import chunk_text
from pyflow.registry import NodeRegistry, registry


def n(id, type, **params):
    return {"id": id, "type": type, "params": params}


def e(id, source, target, target_handle="value", source_handle="result"):
    return dict(id=id, source=source, target=target, target_handle=target_handle, source_handle=source_handle)


def graph(nodes, edges=None):
    return GraphDefinition(nodes=nodes, edges=edges or [])


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.mark.parametrize("g,match", [
    (graph([n("a", "missing"), n("b", "preview")], [e("x", "a", "b")]), "unknown node"),
    (graph([n("a", "count", value="abc"), n("b", "normalize_text")], [e("x", "a", "b", "text")]), "incompatible"),
    (graph([n("a", "text_input"), n("b", "text_input"), n("c", "preview")], [e("x", "a", "c"), e("y", "b", "c")]), "multiple"),
    (graph([n("a", "normalize_text")]), "required"),
    (graph([n("a", "text_input")], [e("x", "a", "z")]), "missing node"),
    (graph([n("a", "text_input"), n("a", "text_input")]), "unique"),
    (graph([n("a", "text_input")], [e("x", "a", "a", "text")]), "cycle"),
    (graph([n("a", "text_input", text=1)]), "expected str"),
    (graph([n("a", "text_input", typo=True)]), "unknown parameter"),
    (graph([]), "at least one"),
])
def test_invalid_graphs_are_validation_errors(client, g, match):
    body = g.model_dump()
    response = client.post("/api/graphs/validate", json=body)
    assert response.status_code == 200
    assert not response.json()["valid"]
    assert match in " ".join(response.json()["errors"])
    assert client.post("/api/runs", json=body).status_code == 422
    assert client.post("/api/runs/stream", json=body).status_code == 422


def test_catalog_types(client):
    catalog = {n["type"]: n for n in client.get("/api/nodes").json()}
    assert catalog["preview"]["inputs"][0]["type"] == "any"
    assert catalog["normalize_text"]["outputs"][0]["type"] == "str"
    assert catalog["chunk_text"]["outputs"][0]["type"] == "list[str]"


@pytest.mark.asyncio
async def test_dict_output_and_multiple_ports():
    r = NodeRegistry()
    def source() -> dict:
        return {"text": "hello"}
    def split(value: dict) -> dict:
        return {"text": value["text"], "length": len(value["text"])}
    def sink(value: str) -> str:
        return value
    r.register(source)
    r.register(split, outputs={"text": str, "length": int})
    r.register(sink)
    g = graph([n("a", "source"), n("b", "split"), n("c", "sink")], [e("x", "a", "b"), e("y", "b", "c", source_handle="text")])
    result = await GraphExecutor(r).execute(g)
    assert result.status == "succeeded"
    assert result.nodes[-1].result.value == "hello"


@pytest.mark.asyncio
async def test_failure_skips_descendants_but_independent_branch_runs():
    g = graph([n("a", "chunk_text", text="abc", size=1, overlap=1), n("b", "preview"), n("c", "preview"), n("d", "text_input")], [e("x", "a", "b"), e("y", "b", "c")])
    result = await GraphExecutor().execute(g)
    statuses = {n.node_id: n.status for n in result.nodes}
    assert statuses == {"a": "failed", "b": "skipped", "c": "skipped", "d": "succeeded"}


@pytest.mark.asyncio
async def test_parallel_tasks_reach_barrier_and_join_waits():
    # A barrier proves concurrency without relying on wall-clock thresholds.
    r = NodeRegistry()
    ready = asyncio.Event()
    arrived = 0
    async def worker(value: int) -> int:
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), timeout=1)
        return value
    def join(a: int, b: int) -> int:
        return a + b
    r.register(worker)
    r.register(join)
    result = await GraphExecutor(r).execute(graph([n("a", "worker", value=2), n("b", "worker", value=3), n("c", "join")], [e("x", "a", "c", "a"), e("y", "b", "c", "b")]))
    assert result.status == "succeeded"
    assert result.nodes[-1].result.value == 5


@pytest.mark.asyncio
async def test_concurrency_limit():
    r = NodeRegistry()
    active, peak = 0, 0
    async def worker() -> int:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(.01)
        active -= 1
        return 1
    r.register(worker)
    result = await GraphExecutor(r, max_concurrency=2).execute(graph([n(str(i), "worker") for i in range(6)]))
    assert result.status == "succeeded"
    assert peak == 2


@pytest.mark.parametrize("kind", ["wrong_type", "missing_port", "not_json", "dynamic_input"])
@pytest.mark.asyncio
async def test_bad_outputs_are_node_failures(kind):
    r = NodeRegistry()
    def source() -> Any:
        if kind == "missing_port":
            return NodeResult(outputs={"wrong": 1})
        if kind == "not_json":
            return object()
        return 42
    def sink(value: str) -> str:
        return value
    r.register(source, outputs={"result": str if kind == "wrong_type" else Any})
    r.register(sink)
    result = await GraphExecutor(r).execute(graph([n("a", "source"), n("b", "sink")], [e("x", "a", "b")]))
    assert result.status == "failed"
    assert len(result.nodes) == 2
    assert result.nodes[-1].status == ("failed" if kind == "dynamic_input" else "skipped")


@pytest.mark.parametrize("value,selected", [(True, "t"), (False, "f"), (None, "f")])
def test_switch_routes_and_streams(client, value, selected):
    g = graph([n("a", "inject", value=value), n("s", "switch", operator="truthy"), n("t", "debug"), n("f", "debug")], [e("1", "a", "s"), e("2", "s", "t", source_handle="true"), e("3", "s", "f", source_handle="false")])
    response = client.post("/api/runs/stream", json=g.model_dump())
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    result = events[-1]["result"]
    assert events[-1]["event"] == "complete"
    assert result["status"] == "succeeded"
    by_id = {n["node_id"]: n for n in result["nodes"]}
    assert by_id[selected]["status"] == "succeeded"
    assert by_id["f" if selected == "t" else "t"]["status"] == "skipped"
    assert any(e.get("node", {}).get("status") == "running" for e in events)


def test_change_select_debug_pipeline(client):
    g = graph([n("a", "inject", value={"name": "old"}), n("b", "change", key="name", replacement="한국어"), n("c", "select_field", path="name"), n("d", "debug")], [e("1", "a", "b"), e("2", "b", "c"), e("3", "c", "d")])
    response = client.post("/api/runs", json=g.model_dump())
    assert response.status_code == 200
    assert response.json()["nodes"][-1]["result"]["value"] == "한국어"


def test_chunker_does_not_emit_redundant_overlap():
    assert chunk_text("12345", size=5, overlap=4).value == ["12345"]
    assert chunk_text("", size=5, overlap=4).value == []


def test_duplicate_registration_rejected():
    r = NodeRegistry()
    def f():
        pass
    r.register(f)
    with pytest.raises(ValueError, match="Duplicate"):
        r.register(f)


@pytest.mark.asyncio
async def test_mutating_branch_does_not_change_sibling_or_source():
    r = NodeRegistry()
    changed = asyncio.Event()
    def source() -> dict:
        return {"value": "original"}
    async def mutate(value: dict) -> dict:
        value["value"] = "changed"
        changed.set()
        return value
    async def observe(value: dict) -> dict:
        await asyncio.wait_for(changed.wait(), 1)
        return value
    for fn in (source, mutate, observe):
        r.register(fn)
    result = await GraphExecutor(r).execute(graph([n("a", "source"), n("b", "mutate"), n("c", "observe")], [e("1", "a", "b"), e("2", "a", "c")]))
    assert result.status == "succeeded"
    by_id = {n.node_id: n for n in result.nodes}
    assert by_id["a"].result.value == by_id["c"].result.value == {"value": "original"}


@pytest.mark.asyncio
async def test_cancelled_run_cleans_up_async_tasks():
    r = NodeRegistry()
    started, stopped = asyncio.Event(), asyncio.Event()
    async def slow() -> str:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
        return "unreachable"
    r.register(slow)
    task = asyncio.create_task(GraphExecutor(r).execute(graph([n("a", "slow")])))
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()
