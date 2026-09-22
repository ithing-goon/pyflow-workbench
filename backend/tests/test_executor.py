import pytest

from pyflow.executor import GraphExecutor
from pyflow.models import GraphDefinition
from pyflow.registry import NodeRegistry


def make_registry():
    registry = NodeRegistry()

    def source(value: int = 2) -> int:
        return value

    def multiply(value: int, factor: int = 3) -> int:
        return value * factor

    registry.register(source)
    registry.register(multiply)
    return registry


@pytest.mark.asyncio
async def test_executes_connected_graph():
    executor = GraphExecutor(make_registry())
    graph = GraphDefinition.model_validate({
        "nodes": [
            {"id": "a", "type": "source", "params": {"value": 4}},
            {"id": "b", "type": "multiply", "params": {"factor": 5}},
        ],
        "edges": [{"id": "e", "source": "a", "target": "b", "target_handle": "value"}],
    })
    result = await executor.execute(graph)
    assert result.status == "succeeded"
    assert result.nodes[-1].result.value == 20


def test_rejects_cycle():
    executor = GraphExecutor(make_registry())
    graph = GraphDefinition.model_validate({
        "nodes": [
            {"id": "a", "type": "source", "params": {"value": 1}},
            {"id": "b", "type": "multiply", "params": {"factor": 2}},
        ],
        "edges": [
            {"id": "e1", "source": "a", "target": "b", "target_handle": "value"},
            {"id": "e2", "source": "b", "target": "a", "target_handle": "value"},
        ],
    })
    validation = executor.validate(graph)
    assert not validation.valid
    assert "cycle" in validation.errors[0]
