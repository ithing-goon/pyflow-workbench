# PyFlow Workbench 0.3

Python-native visual DAG workbench, developed in tested increments toward Node-RED-style workflows.

Continuing in Codex? Start with [the handoff](docs/CODEX_HANDOFF.md) and [the planned v0.4 scope](docs/V0.4_SCOPE.md).

Repository: https://github.com/ithing-goon/pyflow-workbench

```bash
git clone https://github.com/ithing-goon/pyflow-workbench.git
cd pyflow-workbench
```

## Working features

- Python `@node` functions → typed node palette.
- Graph validation and strict runtime input/output checks.
- Concurrent independent nodes (up to 8 per run), structured failures and skipped descendants.
- Seventeen nodes: the original eleven plus Merge, Split, Join, Subflow Input, Subflow and Map Subflow.
- Merge rejoins active branches in deterministic port order, preserving actual null values.
- Indexed Split/Join batches retain order; Map Subflow processes their items concurrently.
- Reusable JSON subflows can be defined, opened, edited, invoked and exported with the parent flow.
- Drag-and-connect editor, editable parameters, disconnect and node deletion.
- Manual Run pipeline; Inject supplies JSON input on every run.
- True/false Switch routing with an explicitly skipped inactive branch.
- Live node status via streamed HTTP events, output JSON, logs and metrics.
- Explicit Save draft and automatic restoration of that saved draft on reload.
- Graph JSON import/export, Document, Switch, Merge and Batch + subflow examples.
- Offline system fonts; no external font requests.

## Quick start: Linux/macOS

Requirements: Python 3.11+, Node.js 20.19+ (or 22.12+).

```bash
./scripts/dev.sh
```

Open http://localhost:5173. Python API docs: http://localhost:8000/docs.

The script installs dependencies when absent. After dependency changes, run `backend/.venv/bin/pip install -e 'backend[dev]'` and `npm --prefix frontend ci` again.

## Windows PowerShell

Run from the project root:

```powershell
py -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
npm --prefix frontend ci
backend\.venv\Scripts\python.exe -m uvicorn pyflow.api:app --app-dir backend --reload
```

In a second terminal, from the same root:

```powershell
npm --prefix frontend run dev
```

Open http://localhost:5173. Dependencies require package registry access for the first installation; running the included examples requires no external service.

## Use the editor

1. Run the Document example and inspect Debug output.
2. Select a node to edit unconnected inputs. `any`, lists and objects use JSON: strings need double quotes.
3. Add nodes by clicking the palette and connect output handles to input handles. Each input accepts one connection. Use Disconnect in the inspector to remove it.
4. Validate checks the complete graph. Run streams real node states. Editing is locked for the duration of a run.
5. Switch example routes a truthy injected value to the true Debug branch. Change Inject `value` to JSON `false` to exercise the false branch.
6. Save draft explicitly before reloading or changing examples. One draft is kept in this browser. Export creates a portable `pyflow-graph.json` file; Import loads it without overwriting the saved draft until Save is pressed.

## Try this increment

**Merge example:** Run it, then change the Inject value to `false` or `null`. One branch is skipped and the other reaches Merge and the final Debug. Merge waits for both branches to settle. Its `first` mode chooses left before right among available values; `all` returns the available values in that order. Missing literals are omitted, while an explicitly entered JSON `null` is a real contribution. Upstream failures are not silently ignored.

**Batch + subflow:** Run the included example. It splits two text values, applies `clean_text` to each, joins them in their original order and displays `["alpha beta", "한국어 문서"]`. Open Subflow trace to inspect each item and inner node.

**Edit a subflow:** Click `Open clean_text`, edit its internal graph, select its output node and port, then click `Define subflow` using the same name. Click `Back to parent flow`, then Save draft or Export. Defining only updates the in-memory library; Save/Export persists it. Saving while inside a subflow saves that canvas as the top-level draft, so return first if you want to preserve the parent canvas as the draft.

**Create a new subflow:** Add exactly one Subflow Input node to a canvas, connect the body, select its output node and use Define canvas as subflow with a new name. Choose New flow to assemble a parent while retaining the library, then use `Use <name>` or `Map <name>` from the Subflows panel. A subflow has one external value input and one selected output port. Its internal nodes may still have multiple ports.

`flow` is a static subflow name, not a dynamic input connection. Subflow references may be nested to depth 8; recursive references are rejected. Batches are finite (up to 1000 items), and a root run has a 5000-node scheduling budget including all nested executions. A failed or inactive map item fails the batch rather than silently dropping that item.

All leaf functions inside nested subflows and batch items share the root run's concurrency limit. Orchestrators do not hold a worker slot while waiting for children, so nesting still works with a one-slot limit. Async cancellation cleans up nested async tasks; running sync threads still cannot be force-killed.

## Add Python nodes

Add functions to `backend/pyflow/nodes.py`, or import your node module during API startup. Restart the API and reload the editor to refresh its catalog.

```python
from pyflow import node

@node(category="Text")
def uppercase(text: str) -> str:
    return text.upper()
```

A normal dictionary return stays under the `result` port. For logs and metrics, declare the payload type separately from its envelope:

```python
from pyflow.models import NodeResult

@node(category="Text", outputs={"result": str})
def uppercase_logged(text: str) -> NodeResult:
    value = text.upper()
    return NodeResult(value=value, outputs={"result": value}, logs=["Converted text"])
```

## Tests and production build

```bash
./scripts/test.sh
./scripts/build.sh
backend/.venv/bin/python scripts/smoke_http.py
```

Windows:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests
npm --prefix frontend test
npm --prefix frontend run build
backend\.venv\Scripts\python.exe scripts\smoke_http.py
```

After building, a single server can serve both the UI and API:

```bash
backend/.venv/bin/python -m uvicorn pyflow.api:app --app-dir backend --host 127.0.0.1 --port 8000
```

Then open http://localhost:8000. Build before starting this server. The local saved draft is origin-specific, so use Export/Import when switching between ports 5173 and 8000.

## Current scope

This is a trusted local Python runtime. No Node-RED JSON/npm compatibility, loop runtime, persistent run history, retry/timeout controls, scheduled triggers, external service nodes or multi-user isolation is implemented yet. Sync Python tasks run in threads and cannot be force-killed. Use Merge to rejoin Switch branches; ordinary nodes still require all upstream inputs. Split/Map/Join use finite batch envelopes, not Node-RED's long-lived message-stream protocol.

See [the execution contract and incremental roadmap](docs/ARCHITECTURE.md) and [test evidence and remaining browser verification](docs/TESTING.md).
