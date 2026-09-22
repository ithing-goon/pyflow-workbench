# PyFlow Workbench: agent instructions

Read `docs/CODEX_HANDOFF.md`, `docs/ARCHITECTURE.md` and `docs/V0.4_SCOPE.md` before changing execution behavior. Read `README.md` for installation and platform-specific commands.

## Project direction

Build a Python-native visual pipeline editor in tested increments inspired by Node-RED. Continue the existing v0.3 project; do not scaffold another application. v0.4 is planned, not implemented. User-facing explanations should be in Korean.

## Runtime invariants

- Preserve strict input/output validation and graph JSON compatibility.
- JSON null is a value. Inactive branches use explicit skipped outputs.
- All leaf executions in one root run share the concurrency limiter. Orchestrators must not occupy a slot while awaiting children.
- Preserve deterministic Merge port order and Map item order, scoped child events and failure traces.
- Async cancellation must clean up owned tasks. Python worker threads cannot be force-killed.
- Retry is opt-in, must not overlap attempts, and must not silently replay whole subflows or maps.

## Verification

Run relevant regression tests while implementing. Before declaring an increment complete, run backend/frontend tests, the production build and real HTTP smoke test using README commands. The baseline recorded for v0.3 is 61 backend + 20 frontend tests.

Frontend App tests mock the graph canvas; they are not real browser drag tests. Record actual checks, failures and remaining gaps accurately. Do not claim browser verification based on component tests.

Keep implementation changes and documentation consistent. Do not commit virtual environments, dependencies, build output, credentials or run artifacts. Follow the current user's instructions about commits and remote pushes. The public repository is https://github.com/ithing-goon/pyflow-workbench.
