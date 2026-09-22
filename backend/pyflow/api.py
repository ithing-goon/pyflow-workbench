from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from . import nodes as _builtin_nodes  # noqa: F401
from .executor import GraphExecutor
from .models import GraphDefinition, RunResult, ValidationResult
from .registry import registry

app = FastAPI(title="PyFlow Workbench API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
executor = GraphExecutor()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/nodes")
def list_nodes():
    return registry.catalog()


@app.post("/api/graphs/validate", response_model=ValidationResult)
def validate_graph(graph: GraphDefinition) -> ValidationResult:
    return executor.validate(graph)


@app.post("/api/runs", response_model=RunResult)
async def run_graph(graph: GraphDefinition) -> RunResult:
    try:
        return await executor.execute(graph)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/runs/stream")
async def stream_graph(graph: GraphDefinition):
    validation = executor.validate(graph)
    if not validation.valid:
        raise HTTPException(status_code=422, detail="; ".join(validation.errors))

    async def events():
        queue: asyncio.Queue = asyncio.Queue()

        async def run():
            try:
                result = await executor.execute(graph, on_event=queue.put_nowait)
                queue.put_nowait({"event": "complete", "result": result.model_dump(mode="json")})
            except Exception as exc:
                queue.put_nowait({"event": "error", "error": str(exc)})
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(run())
        try:
            while (event := await queue.get()) is not None:
                yield json.dumps(event, ensure_ascii=False) + "\n"
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# A local production build can be served by the same Python process.
dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True), name="editor")
