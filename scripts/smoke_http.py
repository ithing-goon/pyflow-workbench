"""Start real local servers, test HTTP + streaming through Vite, then stop them.

Run with backend/.venv/bin/python scripts/smoke_http.py after npm install.
The test uses ports 8000 and 5173; both must be free.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    for port in (8000, 5173):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise RuntimeError("npm is required")
    # Invoke Vite directly so cleanup owns the actual process on every platform.
    node = shutil.which("node")
    processes = []
    with tempfile.TemporaryFile(mode="w+") as log:
        try:
            processes.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "pyflow.api:app", "--app-dir", str(ROOT / "backend"), "--host", "127.0.0.1", "--port", "8000"], stdout=log, stderr=log))
            processes.append(subprocess.Popen([node, str(ROOT / "frontend/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", "5173", "--strictPort"], cwd=ROOT / "frontend", stdout=log, stderr=log))
            with httpx.Client(trust_env=False, timeout=5) as client:
                for url in ("http://127.0.0.1:8000/health", "http://127.0.0.1:5173"):
                    for attempt in range(50):
                        if any(p.poll() is not None for p in processes):
                            raise RuntimeError("A server exited during startup")
                        try:
                            if client.get(url).status_code == 200:
                                break
                        except httpx.ConnectError:
                            pass
                        time.sleep(.1)
                    else:
                        raise RuntimeError(f"Server startup timed out: {url}")
                base = "http://127.0.0.1:5173"
                assert '<div id="root">' in client.get(base).text
                if (ROOT / "frontend/dist/index.html").exists():
                    production_page = client.get("http://127.0.0.1:8000/")
                    assert production_page.status_code == 200 and '<div id="root">' in production_page.text
                    print("PASS single-process production UI serving")
                catalog = client.get(base + "/api/nodes").json()
                assert len(catalog) == 17
                graph = {"nodes": [
                    {"id":"a","type":"inject","params":{"value":{"name":"한국어"}}},
                    {"id":"b","type":"select_field","params":{"path":"name"}},
                    {"id":"c","type":"debug"},
                ], "edges": [
                    {"id":"1","source":"a","target":"b","target_handle":"value"},
                    {"id":"2","source":"b","target":"c","target_handle":"value"},
                ]}
                result = client.post(base + "/api/runs", json=graph)
                assert result.status_code == 200
                assert result.json()["nodes"][-1]["result"]["outputs"] == {"result":"한국어"}
                print("PASS frontend HTTP, API proxy, 17-node catalog, Korean JSON pipeline")
                graph = {"nodes":[{"id":"a","type":"delay","params":{"value":"A","milliseconds":250}},{"id":"b","type":"delay","params":{"value":"B","milliseconds":250}}],"edges":[]}
                started = time.perf_counter()
                with client.stream("POST", base + "/api/runs/stream", json=graph) as stream:
                    assert stream.status_code == 200
                    events = [(time.perf_counter() - started, json.loads(line)) for line in stream.iter_lines() if line]
                duration = time.perf_counter() - started
                running = [t for t, e in events if e.get("node", {}).get("status") == "running"]
                finished = [t for t, e in events if e.get("node", {}).get("status") == "succeeded"]
                assert len(running) == len(finished) == 2
                assert max(running) < min(finished)
                assert events[-1][1]["result"]["status"] == "succeeded"
                print(f"PASS streaming over Vite: both running events precede completion; two 250ms nodes: {duration*1000:.0f}ms")
                bad = {"nodes":[{"id":"a","type":"missing"},{"id":"b","type":"debug"}],"edges":[{"id":"1","source":"a","target":"b","target_handle":"value"}]}
                assert client.post(base + "/api/runs", json=bad).status_code == 422
                assert client.post(base + "/api/runs/stream", json=bad).status_code == 422
                print("PASS invalid graph returns 422 for normal and streaming execution")
                def node(id, type, **params):
                    return {"id":id,"type":type,"params":params}
                def edge(id, source, target, port="value", out="result"):
                    return {"id":id,"source":source,"target":target,"target_handle":port,"source_handle":out}
                merge = {"nodes":[node("s","switch",value=False,operator="truthy"),node("t","debug"),node("f","debug"),node("m","merge"),node("out","debug")],"edges":[edge("1","s","t",out="true"),edge("2","s","f",out="false"),edge("3","t","m","left"),edge("4","f","m","right"),edge("5","m","out")]}
                for value in (True,False,None):
                    merge["nodes"][0]["params"]["value"] = value
                    result=client.post(base+"/api/runs",json=merge)
                    assert result.status_code==200 and result.json()["status"]=="succeeded"
                    assert result.json()["nodes"][-1]["result"]["value"] is value
                print("PASS live HTTP merge of true, false and null routes")
                clean={"nodes":[node("in","subflow_input"),node("clean","normalize_text")],"edges":[edge("1","in","clean","text")],"output_node":"clean","output_handle":"result"}
                mapped={"nodes":[node("s","split",value=["  alpha   beta  ","한국어   문서"]),node("m","map_subflow",flow="clean"),node("j","join")],"edges":[edge("1","s","m"),edge("2","m","j")],"subflows":{"clean":clean}}
                with client.stream("POST",base+"/api/runs/stream",json=mapped) as stream:
                    assert stream.status_code==200
                    events=[json.loads(line) for line in stream.iter_lines() if line]
                terminal=events[-1]["result"]
                assert terminal["status"]=="succeeded"
                assert terminal["nodes"][-1]["result"]["value"]==["alpha beta","한국어 문서"]
                assert len(terminal["nodes"][1]["result"]["child_runs"])==2
                assert any(event.get("scope")==["m","item:0"] for event in events)
                print("PASS live streamed Split -> Map Subflow -> Join; nested scopes and Korean outputs")
        except Exception:
            log.seek(0)
            print(log.read(), file=sys.stderr)
            raise
        finally:
            for p in processes:
                p.terminate()
            for p in processes:
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()


if __name__ == "__main__":
    main()
