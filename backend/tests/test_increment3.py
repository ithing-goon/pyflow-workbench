import asyncio
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from pyflow.api import app
from pyflow.batch import Batch, split_value, join_value
from pyflow.executor import GraphExecutor
from pyflow.models import GraphDefinition, SubflowDefinition, GraphNode, GraphEdge
from pyflow.registry import NodeRegistry, registry


def n(id, type, **params):
    return dict(id=id, type=type, params=params)


def e(id, source, target, port="value", out="result"):
    return dict(id=id, source=source, target=target, target_handle=port, source_handle=out)


def g(nodes, edges=None, subflows=None):
    return GraphDefinition(nodes=nodes, edges=edges or [], subflows=subflows or {})


def clean_flow():
    return SubflowDefinition(nodes=[n("in", "subflow_input"), n("clean", "normalize_text")], edges=[e("1", "in", "clean", "text")], output_node="clean")


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [True, False, None])
async def test_switch_merge_indirect_branches_and_null(value):
    graph = g([n("a", "inject", value=value), n("s", "switch", operator="truthy"), n("t", "debug"), n("f", "debug"), n("m", "merge"), n("d", "debug")], [e("1", "a", "s"), e("2", "s", "t", out="true"), e("3", "s", "f", out="false"), e("4", "t", "m", "left"), e("5", "f", "m", "right"), e("6", "m", "d")])
    result = await GraphExecutor().execute(graph)
    assert result.status == "succeeded"
    assert result.nodes[-1].result.value is value
    assert result.nodes[-1].status == "succeeded"


@pytest.mark.asyncio
async def test_merge_all_order_and_literal_null():
    graph = g([n("a", "delay", value="left", milliseconds=20), n("b", "inject", value="right"), n("m", "merge", mode="all")], [e("2", "b", "m", "right"), e("1", "a", "m", "left")])
    result = await GraphExecutor().execute(graph)
    assert result.nodes[-1].result.value == ["left", "right"]
    result = await GraphExecutor().execute(g([n("m", "merge", left=None)]))
    assert result.nodes[0].status == "succeeded" and result.nodes[0].result.value is None


@pytest.mark.asyncio
async def test_merge_all_inactive_skips():
    graph = g([n("a", "switch", value=False, operator="truthy"), n("b", "switch", value=False, operator="truthy"), n("m", "merge"), n("d", "debug")], [e("1", "a", "m", "left", "true"), e("2", "b", "m", "right", "true"), e("3", "m", "d")])
    result = await GraphExecutor().execute(graph)
    assert result.status == "succeeded"
    assert result.nodes[-1].skip_reason == "branch"


@pytest.mark.asyncio
async def test_merge_does_not_hide_failure_through_skipped_node():
    graph = g([n("a", "chunk_text", text="x", size=0), n("b", "debug"), n("m", "merge", right="good")], [e("1", "a", "b"), e("2", "b", "m", "left")])
    result = await GraphExecutor().execute(graph)
    assert result.status == "failed"
    assert result.nodes[-1].skip_reason == "upstream_error"


@pytest.mark.parametrize("value,separator", [([], "\n"), ([1,None,{"a":2}], "\n"), ("", "\n"), ("a\n\nb\n", "\n"), ("한국어|text", "|")])
def test_split_join_roundtrip_and_order(value, separator):
    batch = split_value(value, separator)
    batch["items"].reverse()
    assert join_value(batch) == value


@pytest.mark.parametrize("change", ["missing", "duplicate", "index", "count", "id"])
def test_join_rejects_corrupt_batch(change):
    batch = split_value([1,2], "\n")
    if change == "missing": batch["items"].pop()
    if change == "duplicate": batch["items"][1]["index"] = 0
    if change == "index": batch["items"][1]["index"] = 10
    if change == "count": batch["count"] = 99
    if change == "id": batch["batch_id"] = ""
    with pytest.raises(ValueError): join_value(batch)


def test_batch_limit_and_text_type_checks():
    with pytest.raises(ValueError): split_value(list(range(1001)), "\n")
    with pytest.raises(ValueError): split_value("text", "")
    batch = split_value("a|b", "|")
    batch["items"][0]["value"] = 1
    with pytest.raises(ValueError): join_value(batch)


@pytest.mark.asyncio
async def test_subflow_reuse_scope_and_no_single_slot_deadlock():
    graph = g([n("a", "subflow", flow="clean", value="one   two"), n("b", "subflow", flow="clean", value="세   글자")], subflows={"clean":clean_flow()})
    before = graph.model_dump()
    events = []
    result = await asyncio.wait_for(GraphExecutor(max_concurrency=1).execute(graph,events.append), 2)
    assert result.status == "succeeded"
    assert [n.result.value for n in result.nodes] == ["one two", "세 글자"]
    assert all(len(n.result.child_runs) == 1 for n in result.nodes)
    assert graph.model_dump() == before
    assert {tuple(e["scope"]) for e in events} == {(), ("a",), ("b",)}


@pytest.mark.asyncio
async def test_nested_subflow_and_failure_trace():
    outer = SubflowDefinition(nodes=[n("in","subflow_input"),n("child","subflow",flow="clean")], edges=[e("1","in","child")], output_node="child")
    graph = g([n("call", "subflow", flow="outer", value="text   value")], subflows={"clean":clean_flow(),"outer":outer})
    result = await GraphExecutor(max_concurrency=1).execute(graph)
    assert result.nodes[0].result.value == "text value"
    graph.nodes[0].params["value"] = 42
    result = await GraphExecutor().execute(graph)
    assert result.status == "failed"
    assert result.nodes[0].result.child_runs[0].status == "failed"
    assert result.nodes[0].result.child_runs[0].nodes[-1].result.child_runs[0].status == "failed"


@pytest.mark.asyncio
async def test_map_subflow_join_and_empty():
    for values in (["  alpha   beta  ","한국어   문서"], []):
        graph = g([n("s","split",value=values),n("m","map_subflow",flow="clean"),n("j","join")], [e("1","s","m"),e("2","m","j")], {"clean":clean_flow()})
        result = await GraphExecutor(max_concurrency=1).execute(graph)
        assert result.status == "succeeded"
        assert result.nodes[-1].result.value == (["alpha beta","한국어 문서"] if values else [])
        assert len(result.nodes[1].result.child_runs) == len(values)
        assert result.nodes[0].result.value["batch_id"] == result.nodes[1].result.value["batch_id"]


@pytest.mark.asyncio
async def test_map_failure_never_emits_partial_join():
    graph = g([n("s","split",value=["ok",42]),n("m","map_subflow",flow="clean"),n("j","join")], [e("1","s","m"),e("2","m","j")], {"clean":clean_flow()})
    result = await GraphExecutor().execute(graph)
    assert result.status == "failed"
    assert result.nodes[-1].status == "skipped"
    assert len(result.nodes[1].result.child_runs) == 2


@pytest.mark.asyncio
async def test_map_order_and_shared_concurrency_cap():
    r = NodeRegistry()
    for entry in registry._nodes.values():
        r.register(entry.function, name=entry.schema.type, outputs=entry.output_types, kind=entry.schema.kind)
    active, peak, finished = 0, 0, []
    async def work(value: int) -> int:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(.01 * (4-value))
        active -= 1
        finished.append(value)
        return value * 10
    r.register(work)
    flow = SubflowDefinition(nodes=[n("in","subflow_input"),n("work","work")],edges=[e("1","in","work")],output_node="work")
    result = await GraphExecutor(r,max_concurrency=2).execute(g([n("m","map_subflow",flow="work",value=split_value([1,2,3],"\n"))],subflows={"work":flow}))
    assert result.status == "succeeded"
    assert peak == 2
    assert finished[0] == 2
    assert join_value(result.nodes[0].result.value) == [10,20,30]


@pytest.mark.parametrize("issue", ["recursive", "missing_input", "bad_output", "unknown_flow", "dynamic_flow", "input_edge"])
def test_invalid_subflows_fail_preflight(issue):
    flow = clean_flow()
    graph = g([n("call","subflow",value="x",flow="clean")],subflows={"clean":flow})
    if issue == "recursive":
        flow.nodes.append(GraphNode(**n("recurse","subflow",flow="clean",value="x")))
        graph.subflows["clean"] = SubflowDefinition.model_validate(flow.model_dump())
    if issue == "missing_input": graph.subflows["clean"].nodes[0].type = "inject"
    if issue == "bad_output": graph.subflows["clean"].output_node = "missing"
    if issue == "unknown_flow": graph.nodes[0].params["flow"] = "missing"
    if issue == "dynamic_flow":
        graph = g([n("a","inject",value="clean"),n("call","subflow",value="x",flow="clean")],[e("x","a","call","flow")],{"clean":flow})
    if issue == "input_edge":
        graph.subflows["clean"].nodes.append(GraphNode(**n("a","inject",value="x")))
        graph.subflows["clean"].edges.append(GraphEdge(**e("extra","a","in")))
        graph.subflows["clean"] = SubflowDefinition.model_validate(graph.subflows["clean"].model_dump())
    with TestClient(app,raise_server_exceptions=False) as client:
        response = client.post('/api/runs/stream',json=graph.model_dump())
    assert response.status_code == 422, response.text


def test_nested_stream_is_serializable_and_scoped():
    graph = g([n("call","subflow",flow="clean",value="a   b")],subflows={"clean":clean_flow()})
    with TestClient(app) as client:
        response = client.post('/api/runs/stream',json=graph.model_dump())
    events = [json.loads(line) for line in response.text.splitlines()]
    child = events[-1]['result']['nodes'][0]['result']['child_runs'][0]
    assert child['status'] == 'succeeded'
    assert child['nodes'][-1]['result']['value'] == 'a b'
    assert events[-1]['event'] == 'complete'
    assert any(e.get('scope') == ['call'] for e in events)


@pytest.mark.asyncio
async def test_subflow_inactive_output_and_map_policy():
    body = SubflowDefinition(nodes=[n('in','subflow_input'),n('s','switch',operator='truthy')],edges=[e('1','in','s')],output_node='s',output_handle='true')
    result = await GraphExecutor().execute(g([n('call','subflow',flow='gate',value=False),n('out','debug')],[e('1','call','out')],{'gate':body}))
    assert result.status == 'succeeded'
    assert result.nodes[-1].skip_reason == 'branch'
    result = await GraphExecutor().execute(g([n('call','map_subflow',flow='gate',value=split_value([True,False],'\n'))],subflows={'gate':body}))
    assert result.status == 'failed'
    assert len(result.nodes[0].result.child_runs) == 2


def test_nesting_depth_limit():
    flows={}
    for i in range(9):
        flows[str(i)]=SubflowDefinition(nodes=[n('in','subflow_input'),n('call','subflow',flow=str(i+1))],edges=[e('1','in','call')],output_node='call') if i<8 else SubflowDefinition(nodes=[n('in','subflow_input')],edges=[],output_node='in')
    validation=GraphExecutor().validate(g([n('call','subflow',flow='0',value='x')],subflows=flows))
    assert not validation.valid
    assert any('depth 8' in error for error in validation.errors)


@pytest.mark.asyncio
async def test_map_cancellation_cleans_up_all_workers():
    r=NodeRegistry()
    for entry in registry._nodes.values():
        r.register(entry.function,name=entry.schema.type,outputs=entry.output_types,kind=entry.schema.kind)
    started=asyncio.Event()
    active=0
    async def wait(value: str) -> str:
        nonlocal active
        active+=1
        if active==2: started.set()
        try:
            await asyncio.Event().wait()
        finally:
            active-=1
        return value
    r.register(wait)
    flow=SubflowDefinition(nodes=[n('in','subflow_input'),n('wait','wait')],edges=[e('1','in','wait')],output_node='wait')
    task=asyncio.create_task(GraphExecutor(r,max_concurrency=2).execute(g([n('m','map_subflow',value=split_value(['a','b'],'\n'),flow='wait')],subflows={'wait':flow})))
    await asyncio.wait_for(started.wait(),1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert active==0
