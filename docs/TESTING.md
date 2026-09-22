# Verification of version 0.3

Executed in the shared Linux development environment:

- Python 3.12.14; Node.js 24.19.0.
- Backend: 61 passing tests (29 retained from 0.2 plus 32 new cases).
- Frontend: 20 passing tests (14 retained plus 6 for subflow authoring, serialization, scoped events and Merge).
- TypeScript check and Vite production build: passed.
- Real Uvicorn + Vite HTTP smoke test: passed.
- Seventeen registered nodes, Korean JSON output and the development API proxy: passed.
- Streaming: two independent 250ms delay nodes completed in 266ms in the recorded run; both running events arrived before either completion event. Timing is illustrative; concurrency regression uses a barrier rather than a timing-only assertion.
- Invalid normal and streaming requests returned 422 rather than 500.
- Real HTTP Merge tests for true, false and null routes: passed.
- Real streamed Split → Map Subflow → Join with Korean output and nested scopes: passed.
- Single-process production static UI serving: passed.

## Regression coverage

Unknown source type, missing nodes/ports, duplicate nodes, duplicate input edges, cycles, invalid literals, missing parameters, scalar and dict outputs, named multiple outputs, output type errors, serialization failures, skipped descendants, independent success after a failure, concurrency limit, cancellation cleanup, branch input isolation, true/false/null routing, and Change → Select → Debug processing.

Frontend tests cover draft serialization and restoration, malformed imports, JSON editing without string coercion, integer input validation, connected input disabling, incident-edge deletion, streamed output display, and startup error visibility. App tests replace the graph canvas with a state-testing adapter; they do not prove canvas layout or real mouse dragging.

New runtime tests cover direct and indirect branch merges, all-inactive and failed-ancestor handling, null contributions, left/right ordering, indexed batch round trips, incomplete/duplicate/out-of-range indexes, batch size and text type checks, template isolation, one-slot nested execution, nested failure traces, mapped ordering and a shared concurrency cap, empty and failed maps, recursive/invalid definitions, depth limits, scoped streamed events, inactive subflow outputs, and nested async cancellation cleanup.

New UI tests exercise Open → Define → Back → Use → Save for subflows, preservation of their definitions in exported graph data, same-ID parent/child event separation, Merge example wiring, and omission of unset Merge literals.

## Reproduce

```bash
./scripts/test.sh
./scripts/build.sh
backend/.venv/bin/python scripts/smoke_http.py
```

Windows equivalents are in the README. The HTTP smoke test requires free ports 8000 and 5173 and shuts down the servers it starts.

## Remaining verification gap

Real browser interaction and visual layout were not verified: the available remote browser previously rejected local access with `ERR_BLOCKED_BY_CLIENT`. We did not bypass that restriction. Manually verify port dragging, disconnecting, viewport resizing, file download/upload, and reload after Save draft on the target machine.

The installed Starlette test client emits two dependency deprecation warnings. They do not fail the suite; future dependency updates should preserve this regression gate.
