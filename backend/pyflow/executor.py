from __future__ import annotations

import asyncio
import inspect
import time
from copy import deepcopy
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Callable

from pydantic import TypeAdapter, ValidationError

from .models import GraphDefinition, NodeResult, NodeRun, RunResult, ValidationResult
from .registry import NodeRegistry, compatible, registry
from .batch import Batch


class ChildFailure(Exception):
    def __init__(self, message: str, result: NodeResult):
        super().__init__(message)
        self.result = result


def _topological_order(graph: GraphDefinition) -> list[str]:
    ids = [n.id for n in graph.nodes]
    if not ids:
        raise ValueError("Graph must contain at least one node")
    if len(set(ids)) != len(ids):
        raise ValueError("Node ids must be unique")
    if len({e.id for e in graph.edges}) != len(graph.edges):
        raise ValueError("Edge ids must be unique")
    incoming = dict.fromkeys(ids, 0)
    outgoing = {n: [] for n in ids}
    for edge in graph.edges:
        if edge.source not in incoming or edge.target not in incoming:
            raise ValueError(f"Edge {edge.id} references a missing node")
        incoming[edge.target] += 1
        outgoing[edge.source].append(edge.target)
    ready = deque(n for n in ids if incoming[n] == 0)
    order = []
    while ready:
        current = ready.popleft()
        order.append(current)
        for target in outgoing[current]:
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
    if len(order) != len(ids):
        raise ValueError("Graph contains a cycle; MVP supports DAGs only")
    return order


class GraphExecutor:
    def __init__(self, node_registry: NodeRegistry = registry, max_concurrency: int = 8) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        self.registry = node_registry
        self.max_concurrency = max_concurrency

    def _validate_graph(self, graph: GraphDefinition) -> ValidationResult:
        try:
            order = _topological_order(graph)
        except ValueError as exc:
            return ValidationResult(valid=False, errors=[str(exc)])
        errors, definitions = [], {}
        for node in graph.nodes:
            try:
                definitions[node.id] = self.registry.get(node.type)
            except KeyError:
                errors.append(f"{node.id}: unknown node type '{node.type}'")
        supplied = set()
        for edge in graph.edges:
            key = (edge.target, edge.target_handle)
            if key in supplied:
                errors.append(f"{edge.target}.{edge.target_handle}: multiple incoming edges")
            supplied.add(key)
            source, target = definitions.get(edge.source), definitions.get(edge.target)
            if source is None or target is None:
                continue
            if edge.source_handle not in source.output_types:
                errors.append(f"{edge.source}: unknown output '{edge.source_handle}'")
            elif edge.target_handle not in target.input_types:
                errors.append(f"{edge.target}: unknown input '{edge.target_handle}'")
            elif not compatible(source.output_types[edge.source_handle], target.input_types[edge.target_handle]):
                errors.append(f"{edge.id}: incompatible output and input types")
        for node in graph.nodes:
            definition = definitions.get(node.id)
            if definition is None:
                continue
            kind = definition.schema.kind
            if kind in ("subflow", "map_subflow"):
                if (node.id, "flow") in supplied:
                    errors.append(f"{node.id}: flow must be a static subflow name")
                elif not isinstance(node.params.get("flow"), str) or node.params["flow"] not in graph.subflows:
                    errors.append(f"{node.id}: unknown subflow name")
            if kind == "merge":
                if (node.id, "mode") in supplied or node.params.get("mode", "first") not in ("first", "all"):
                    errors.append(f"{node.id}: merge mode must be static first or all")
                if not any((node.id, port) in supplied or port in node.params for port in ("left", "right")):
                    errors.append(f"{node.id}: merge needs a branch input")
            for name in node.params:
                if name not in definition.input_types:
                    errors.append(f"{node.id}: unknown parameter '{name}'")
            for port in definition.schema.inputs:
                if (node.id, port.name) in supplied:
                    continue
                if port.name not in node.params:
                    if port.required:
                        errors.append(f"{node.id}: required input '{port.name}' is not connected or configured")
                    continue
                try:
                    TypeAdapter(definition.input_types[port.name]).validate_python(node.params[port.name], strict=True)
                except ValidationError:
                    errors.append(f"{node.id}.{port.name}: expected {port.type}")
        return ValidationResult(valid=not errors, errors=errors, order=order)

    def validate(self, graph: GraphDefinition) -> ValidationResult:
        main = self._validate_graph(graph)
        errors = list(main.errors)
        references = {}
        for name, flow in graph.subflows.items():
            body = GraphDefinition(nodes=flow.nodes, edges=flow.edges, subflows=graph.subflows)
            result = self._validate_graph(body)
            errors.extend(f"subflow {name}: {e}" for e in result.errors)
            inputs = [n for n in flow.nodes if n.type == "subflow_input"]
            if len(inputs) != 1:
                errors.append(f"subflow {name}: exactly one subflow_input is required")
            elif any(e.target == inputs[0].id for e in flow.edges):
                errors.append(f"subflow {name}: input node cannot have incoming edges")
            output = next((n for n in flow.nodes if n.id == flow.output_node), None)
            try:
                if output is None or flow.output_handle not in self.registry.get(output.type).output_types:
                    errors.append(f"subflow {name}: invalid output node or port")
            except KeyError:
                errors.append(f"subflow {name}: unknown output node type")
            references[name] = set()
            for n in flow.nodes:
                try:
                    kind = self.registry.get(n.type).schema.kind
                except KeyError:
                    continue
                if kind in ("subflow", "map_subflow") and isinstance(n.params.get("flow"), str):
                    references[name].add(n.params["flow"])
        def depth(name, path):
            if name in path:
                raise ValueError("Recursive subflow reference: " + " -> ".join([*path, name]))
            if len(path) >= 8:
                raise ValueError("Subflow nesting exceeds maximum depth 8")
            for target in references.get(name, []):
                depth(target, [*path, name])
        try:
            for name in references:
                depth(name, [])
        except ValueError as exc:
            errors.append(str(exc))
        return ValidationResult(valid=not errors, errors=errors, order=main.order)

    async def execute(self, graph: GraphDefinition, on_event: Callable[[dict], None] | None = None, *, _context=None, _scope=None) -> RunResult:
        started = datetime.now(timezone.utc)
        validation = self.validate(graph) if _context is None else self._validate_graph(graph)
        if not validation.valid:
            raise ValueError("; ".join(validation.errors))
        by_id = {n.id: n for n in graph.nodes}
        incoming = {n.id: [] for n in graph.nodes}
        for edge in graph.edges:
            incoming[edge.target].append(edge)
        runs = {n.id: NodeRun(node_id=n.id, node_type=n.type, status="pending") for n in graph.nodes}
        completed, tasks = {}, {}
        context = _context if _context is not None else {"semaphore": asyncio.Semaphore(self.max_concurrency), "scheduled": 0}
        context["scheduled"] += len(graph.nodes)
        if context["scheduled"] > 5000:
            raise ValueError("Run exceeded the 5000-node execution budget")
        scope = _scope or []

        @asynccontextmanager
        async def permit(kind):
            # Orchestrators must not hold a worker slot while awaiting their children.
            if kind in ("subflow", "map_subflow"):
                yield
            else:
                async with context["semaphore"]:
                    yield

        def emit(run: NodeRun) -> None:
            if on_event:
                on_event({"event": "node", "scope": scope, "node": run.model_dump(mode="json")})

        async def child_run(flow_name, value, child_scope):
            flow = graph.subflows[flow_name]
            body = GraphDefinition(nodes=deepcopy(flow.nodes), edges=deepcopy(flow.edges), subflows=graph.subflows, name=flow_name)
            next(n for n in body.nodes if n.type == "subflow_input").params["value"] = deepcopy(value)
            child = await self.execute(body, on_event, _context=context, _scope=child_scope)
            output = next(n for n in child.nodes if n.node_id == flow.output_node)
            inactive = output.status == "skipped" or (output.result is not None and flow.output_handle in output.result.skipped_outputs)
            value = output.result.outputs.get(flow.output_handle) if output.result else None
            return child, value, inactive

        async def orchestrate(kind, inputs, node_id):
            if kind == "subflow":
                child, value, inactive = await child_run(inputs["flow"], inputs["value"], [*scope, node_id])
                result = NodeResult(value=value, outputs={} if inactive else {"result": value}, skipped_outputs=["result"] if inactive else [], child_runs=[child])
                if child.status == "failed":
                    raise ChildFailure("Subflow failed; inspect its child run", result)
                return result
            batch = Batch.model_validate(inputs["value"])
            items = sorted(batch.items, key=lambda i: i.index)
            children = [asyncio.create_task(child_run(inputs["flow"], i.value, [*scope, node_id, f"item:{i.index}"])) for i in items]
            try:
                results = await asyncio.gather(*children, return_exceptions=True)
            finally:
                for task in children:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*children, return_exceptions=True)
            child_runs = [r[0] for r in results if not isinstance(r, BaseException)]
            if any(isinstance(r, BaseException) or r[0].status == "failed" or r[2] for r in results):
                details = [str(r) for r in results if isinstance(r, BaseException)]
                raise ChildFailure("Batch subflow failed or returned an inactive output" + (": " + "; ".join(details) if details else ""), NodeResult(child_runs=child_runs))
            for item, (_, value, _) in zip(items, results):
                item.value = value
            batch.items = items
            value = batch.model_dump()
            return NodeResult(value=value, outputs={"result": value}, child_runs=child_runs, metrics={"item_count": len(items)})

        async def execute_node(node_id: str) -> None:
            edges = incoming[node_id]
            for parent in dict.fromkeys(e.source for e in edges):
                await tasks[parent]
            run = runs[node_id]
            instance = by_id[node_id]
            definition = self.registry.get(instance.type)
            kind = definition.schema.kind
            available = [e for e in edges if runs[e.source].status == "succeeded" and e.source_handle not in completed[e.source].skipped_outputs]
            if any(runs[e.source].status == "failed" or runs[e.source].skip_reason == "upstream_error" for e in edges):
                reason, code = "Upstream node failed", "upstream_error"
            elif kind == "merge":
                has_literal = any(p in instance.params and not any(e.target_handle == p for e in edges) for p in ("left", "right"))
                reason, code = (None, None) if available or has_literal else ("All branches inactive", "branch")
            elif len(available) != len(edges):
                reason, code = "Branch not selected", "branch"
            else:
                reason, code = None, None
            if reason:
                run.status, run.error = "skipped", reason
                run.skip_reason = code
                run.finished_at = datetime.now(timezone.utc)
                emit(run)
                return
            async with permit(kind):
                run.status = "running"
                run.started_at = datetime.now(timezone.utc)
                emit(run)
                tick = time.perf_counter()
                try:
                    inputs = {p.name: p.default for p in definition.schema.inputs if not p.required}
                    inputs.update(instance.params)
                    for edge in available:
                        inputs[edge.target_handle] = completed[edge.source].outputs[edge.source_handle]
                    inputs = {k: TypeAdapter(definition.input_types[k]).validate_python(v, strict=True) for k, v in deepcopy(inputs).items()}
                    fn = definition.function
                    if kind == "merge":
                        present = {e.target_handle for e in available} | {p for p in instance.params if not any(e.target_handle == p for e in edges)}
                        values = [inputs[p] for p in ("left", "right") if p in present]
                        raw = values if inputs["mode"] == "all" else values[0]
                    elif kind in ("subflow", "map_subflow"):
                        raw = await orchestrate(kind, inputs, node_id)
                    else:
                        raw = await fn(**inputs) if inspect.iscoroutinefunction(fn) else await asyncio.to_thread(fn, **inputs)
                    if isinstance(raw, NodeResult):
                        result = raw.model_copy(deep=True)
                        if not result.outputs and not result.skipped_outputs and len(definition.output_types) == 1:
                            result.outputs = {next(iter(definition.output_types)): result.value}
                    elif len(definition.output_types) > 1:
                        if not isinstance(raw, dict):
                            raise ValueError("Multiple outputs require a dict or NodeResult")
                        result = NodeResult(value=raw, outputs=raw)
                    else:
                        result = NodeResult.from_value(raw, next(iter(definition.output_types)))
                    active, skipped = set(result.outputs), set(result.skipped_outputs)
                    if active & skipped or active | skipped != set(definition.output_types):
                        raise ValueError("Returned output ports do not match the declared output ports")
                    for name in active:
                        result.outputs[name] = TypeAdapter(definition.output_types[name]).validate_python(result.outputs[name], strict=True)
                    result.metrics.setdefault("latency_ms", round((time.perf_counter() - tick) * 1000, 2))
                    result.model_dump_json()
                    completed[node_id] = result
                    run.result, run.status = result, "succeeded"
                except Exception as exc:
                    if isinstance(exc, ChildFailure):
                        run.result = exc.result
                    run.status = "failed"
                    run.error = f"{type(exc).__name__}: {exc}"
                finally:
                    run.finished_at = datetime.now(timezone.utc)
                    emit(run)

        try:
            for node_id in validation.order:
                tasks[node_id] = asyncio.create_task(execute_node(node_id))
            await asyncio.gather(*tasks.values())
        finally:
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)
        return RunResult(
            status="failed" if any(r.status == "failed" for r in runs.values()) else "succeeded",
            started_at=started, finished_at=datetime.now(timezone.utc),
            nodes=[runs[n] for n in validation.order],
        )
