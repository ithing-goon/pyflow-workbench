# PyFlow 0.3 execution contract

PyFlow is a local, trusted-code DAG workbench inspired by Node-RED. It does not load Node-RED flows or npm nodes and is not yet an event-driven Node-RED-compatible runtime.

## Function and port contract

- Functions use named positional-or-keyword or keyword-only arguments. Variadic and positional-only signatures are rejected.
- `get_type_hints` resolves postponed annotations. JSON catalogs use `any`, `str`, `int`, `float`, `bool`, `list[...]`, and `dict[...]` labels.
- Plain return values, including dictionaries, are always one output named `result` unless a different single output was declared.
- `NodeResult` is a metadata envelope, not the output payload's type. Use `outputs={"result": str}` to declare its payload type. Without this metadata the payload is `Any`.
- Multiple declared ports accept a dictionary keyed by port names or `NodeResult(outputs=...)`.
- A conditional node explicitly lists inactive ports in `skipped_outputs`. JSON `null` is an ordinary value, never an implicit skip marker.
- Active and skipped ports must be disjoint and together match declared ports exactly.
- Every active output and every bound input is validated at runtime. Serialization failures become node failures rather than broken HTTP responses.

## Validation

Graph validation checks nonempty DAGs, unique node and edge IDs, known node types, node/port existence, one edge per input, static type compatibility, required inputs, unknown parameters, and strict literal types. Connected values override literal settings.

`Any` edges are allowed because their type is not known until execution. Actual values are validated against the target annotation before invoking the function. Generic container and union annotations participate in static compatibility; this is deliberately conservative, not a complete Python subtype system.

## Scheduling and failure

- Topological ordering is deterministic for the same node and edge order.
- Each leaf node waits for its parents, then acquires a root-run concurrency semaphore (default 8), shared by all subflows and mapped items. Orchestrator nodes do not acquire it while awaiting children.
- Independent nodes run concurrently; async functions run in the event loop, sync functions in threads.
- Inputs are deep-copied per node, preventing one branch's mutations from affecting another branch or a previous output.
- Failed parents skip descendants with `skip_reason=upstream_error`; inactive branches propagate `skip_reason=branch`. Independent branches continue.
- Ordinary nodes use AND semantics. Merge waits for all parents and ignores branch skips, but not failed ancestors. Its `first`/`all` mode selects contributions in left/right order, never completion order. All inactive inputs skip Merge. Explicit null literals remain available values.
- All nodes appear in the terminal run result. Any failed node makes the run fail; an intentionally skipped branch alone does not.
- Async tasks are cleaned up when execution is cancelled. Running Python threads cannot be forcibly stopped; there is no hard-kill or CPU-isolation guarantee.

## API and state

`GET /api/nodes` returns the registry. `POST /api/graphs/validate` validates a JSON graph. `POST /api/runs` returns a complete run. `POST /api/runs/stream` streams NDJSON `node`, `complete`, and `error` events. Node events include running and terminal states; logs and output arrive when the node finishes, not continuously from inside arbitrary functions.

Requests that fail preflight validation return HTTP 422. Node-level execution failures return structured run results. Streams are transient, with no reconnect/resume protocol or persisted run history.

The editor stores one explicit saved draft in browser localStorage, and imports/exports graph JSON including the optional `subflows` library. It does not store Python source or run data in the draft. Backend graphs and runs are not persisted. The Vite server proxies `/api` to localhost:8000; after building, FastAPI can serve `frontend/dist` from the same origin.

## Subflows and batches

`GraphDefinition.subflows` maps a name to `{nodes, edges, output_node, output_handle}`. Definitions each have exactly one `subflow_input`, with no incoming edges. Execution clones the definition and binds its input value without mutating the template. The selected output may be any declared port. Names referenced by Subflow and Map Subflow must be literal parameters. Preflight validates all definitions, output boundaries, references, cycles and maximum nesting depth (8).

Root and child run results retain their own node IDs. Streamed node events carry a `scope` array: `[]` at the root, `[parentNode]` in a subflow, and `[mapNode, "item:0"]` for a mapped item. Nested scopes append these components. `NodeResult.child_runs` retains completed child results, including partial failure traces. A child's failure fails its parent; an inactive selected output propagates an inactive parent port. The entire subflow must finish before returning its output.

Split emits a finite batch envelope with `batch_id`, `kind` (list/text), `separator`, `count`, and `items: [{index,value}]`. Empty lists have count 0; empty text contains one empty string so text round trips exactly. Map Subflow retains this metadata, runs each item with the shared semaphore, and restores index order. A failed or inactive item fails the map; Join never receives a partial batch. Join validates complete, unique contiguous indexes and restores a list or separator-joined text. Text joins reject non-string transformed values. Mixing batch envelopes is unsupported.

Each batch is capped at 1000 items. A root execution may schedule at most 5000 nodes across all nested runs. Cancellation propagates to nested async tasks and mapped workers; no hard cancellation of Python threads or separate process isolation is provided.

## Increment plan and acceptance gates

| Increment | State | Acceptance gate |
| --- | --- | --- |
| Type/output contracts and concurrent DAG | Implemented | Regression suite and real HTTP smoke test pass |
| Draft save/restore, JSON import/export, Debug | Implemented | Component and graph serialization tests pass |
| Inject, Switch, Change, field selection, live node events | Implemented | Both branch paths and streamed completion pass |
| OR-merge, split/join, reusable subflows | Implemented in 0.3 | Nested scopes, inactive branch merge, batch ordering, shared limiter, cancellation and template isolation tests |
| Retry, timeout, Catch-style error routing | Planned | Idempotency and cancellation contracts defined and tested |
| Persistent run history and restart recovery | Planned | SQLite migrations, restart and replay tests |
| HTTP request, file IO, scheduled triggers | Planned | Connection configuration, resource limits, trigger lifecycle tests |
| Loops, long-lived messages and backpressure | Planned | Explicit message runtime design; not a DAG workaround |

Each future increment must retain the existing test suite. These planned rows are not claims of implementation.
