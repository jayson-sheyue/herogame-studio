#!/usr/bin/env python3
"""Exercise the actual frozen service with an empty profile and minimal PATH."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import uuid

import httpx


def launch(executable, data):
    token = uuid.uuid4().hex + uuid.uuid4().hex
    child = subprocess.Popen([str(executable)], cwd="/", env={"PATH":"/usr/bin:/bin", "HOME":os.path.expanduser("~"), "STUDIO_DATA_DIR":str(data), "STUDIO_DESKTOP_TOKEN":token}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if not select.select([child.stdout], [], [], 45)[0]:
        child.kill(); raise AssertionError("frozen service startup timed out")
    line = child.stdout.readline()
    if not line:
        raise AssertionError("frozen service exited: " + child.stderr.read()[-3000:])
    port = json.loads(line)["port"]
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False)
    assert client.get("/api/health").status_code == 403
    assert client.get("/_desktop/start", params={"token":token}).status_code == 303
    return child, client


def stop(child, client):
    client.close(); child.terminate(); child.wait(timeout=10)
    assert not child.stdout.read().strip(), "unexpected stdout after readiness"


def main():
    executable = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="工坊 打包验收 ") as folder:
        root = Path(folder); data = root / "应用数据"; project = root / "桌宠 工程"
        child, client = launch(executable, data)
        try:
            response = client.get("/api/health"); assert response.status_code == 200
            token = response.headers["X-Studio-Workspace"]
            assert not response.json()["api_key_set"]
            assert "/static/app.js" in client.get("/").text
            for asset in ["app.js", "styles.css"]: assert client.get("/static/"+asset).status_code == 200
            response = client.post("/api/line", json={"kind":"deskpet"}, headers={"X-Studio-Workspace":token}); assert response.status_code == 200, response.text
            token = response.headers["X-Studio-Workspace"]
            project.mkdir()
            response = client.post("/api/projects/use", json={"folder":str(project),"kind":"deskpet"}, headers={"X-Studio-Workspace":token}); assert response.status_code == 200, response.text
            token = response.headers["X-Studio-Workspace"]
            key = "AIza" + "OfflineOnlyDesktopSmoke12345678"
            response = client.post("/api/settings", json={"api_key":key,"text_model":"custom-text-model"}, headers={"X-Studio-Workspace":token}); assert response.status_code == 200, response.text
            assert key not in response.text
            for file in data.rglob("*.json"): assert key not in file.read_text()
            assert (project / "herogame.json").exists()
            assert (data / "projects.json").exists()
        finally: stop(child, client)
        child, client = launch(executable, data)
        try:
            response = client.get("/api/health"); assert response.status_code == 200
            result = response.json()
            assert result["line"] == "deskpet" and result["has_project"]
            assert not result["api_key_set"], "session key must disappear after restart"
            assert result["text_model"] == "custom-text-model"
        finally: stop(child, client)
    print("真实冻结服务检查通过：独立启动、资源、会话隔离、中文路径、工程和设置保留、重启清除会话密钥。未调用云端 API。")


if __name__ == "__main__": main()
