"""Coordinate the single-process studio's shared active workspace.

Keep the lease until the endpoint really finishes, including after a browser
stops waiting. Tokens detect stale tabs; they are not authentication credentials.
"""

from contextlib import contextmanager
import re
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute


WORKSPACE_HEADER = "X-Studio-Workspace"
SWITCH_PATHS = {"/api/line", "/api/line/clear", "/api/projects/use", "/api/projects/wipe"}


class WorkspaceGuard:
    def __init__(self):
        self._lock = Lock()
        self.token = uuid4().hex
        self._active = 0
        self._switching = False
        self._resources = set()

    @contextmanager
    def lease(self, *, token, switch=False, resource=None, mutation=False, health=False):
        with self._lock:
            if not health and ((token and token != self.token) or (mutation and not token)):
                raise HTTPException(409, "工程上下文已变化，请刷新页面后再操作。当前输入尚未提交。")
            if self._switching or (switch and self._active):
                raise HTTPException(409, "工程仍有任务执行中，请等待任务结束后再切换或清空工程。")
            if resource and resource in self._resources:
                raise HTTPException(409, "这份资产仍有操作执行中，请等待完成后重试；当前编辑已保留。")
            self._active += 1
            if switch:
                self._switching = True
            if resource:
                self._resources.add(resource)
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1
                if resource:
                    self._resources.remove(resource)
                if switch:
                    # Failed switches can have partially changed the registry.
                    # Invalidate old tabs even then, rather than risking a write.
                    self.token = uuid4().hex
                    self._switching = False


workspace_guard = WorkspaceGuard()


class WorkspaceRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request: Request):
            path = request.url.path
            # Voice catalog loading does not read or write project assets and
            # can be slow on first import. It must not block the startup gate.
            if not path.startswith("/api/") or path == "/api/tts/voices":
                return await handler(request)
            mutation = request.method not in {"GET", "HEAD", "OPTIONS"}
            resource = None
            if mutation and request.headers.get("content-type", "").split(";")[0] == "application/json":
                try:
                    body = await request.json()
                except ValueError:
                    body = None  # Let FastAPI report malformed input.
                if isinstance(body, dict):
                    for field in ("portrait_id", "hero_id", "stage_id"):
                        if body.get(field):
                            item_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(body[field]).strip().lower()).strip("_")[:48]
                            resource = (field, item_id)
                            break
                    if body.get("kind") == "style":
                        resource = ("style", "anchor")
            elif mutation and request.headers.get("content-type", "").startswith("multipart/form-data"):
                form = await request.form()
                if path in {"/api/heroes/ref-photo", "/api/voice/clone"}:
                    item_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(form.get("hero_id") or "_new").strip().lower()).strip("_")[:48]
                    resource = ("hero_id", item_id)
            if mutation and path.startswith("/api/style/"):
                resource = ("style", "anchor")
            if mutation and path in {"/api/settings", "/api/test-auth"}:
                resource = ("settings", "api")
            with workspace_guard.lease(
                token=request.headers.get(WORKSPACE_HEADER),
                switch=path in SWITCH_PATHS,
                resource=resource,
                mutation=mutation,
                health=path == "/api/health",
            ):
                response = await handler(request)
            response.headers[WORKSPACE_HEADER] = workspace_guard.token
            return response

        return guarded
