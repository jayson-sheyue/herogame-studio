"""Private, owned backend for the macOS shell. No development reloader or logs."""

import asyncio
import hmac
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studio"))


def msg(zh: str, en: str) -> str:
    locale = os.environ.get("STUDIO_UI_LOCALE", "").strip()
    if not locale:
        accept = os.environ.get("HTTP_ACCEPT_LANGUAGE", "") or ""
        locale = "en" if accept.lower().startswith("en") else "zh-CN"
    return en if locale == "en" else zh


class DesktopAccess:
    """A session cookie prevents unrelated local pages from using this backend."""

    def __init__(self, app, token):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from starlette.requests import Request
        from starlette.responses import PlainTextResponse, RedirectResponse
        request = Request(scope, receive)
        host = request.url.hostname
        if host != "127.0.0.1":
            return await PlainTextResponse("Forbidden", 403)(scope, receive, send)
        if scope["path"] == "/_desktop/start":
            if hmac.compare_digest(request.query_params.get("token", ""), self.token):
                response = RedirectResponse("/", 303)
                response.set_cookie("studio_desktop", self.token, httponly=True, samesite="strict")
                response.headers["Cache-Control"] = "no-store"
                response.headers["Referrer-Policy"] = "no-referrer"
                return await response(scope, receive, send)
        authenticated = hmac.compare_digest(request.cookies.get("studio_desktop", ""), self.token)
        origin = request.headers.get("origin")
        # Reject cross-origin writes even if a client happens to send a cookie.
        if not authenticated or (origin and origin != str(request.base_url).rstrip("/")):
            return await PlainTextResponse("Forbidden", 403)(scope, receive, send)
        return await self.app(scope, receive, send)


def main():
    token = os.environ.pop("STUDIO_DESKTOP_TOKEN", "")
    if len(token) < 32 or not os.environ.get("STUDIO_DATA_DIR"):
        raise SystemExit(msg("请从作图工坊客户端启动。", "Please launch from the Hero Studio desktop client."))
    parent = os.getppid()
    import server
    app = DesktopAccess(server.app, token)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    service = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False,
                                          timeout_graceful_shutdown=3, loop="asyncio", http="h11"))

    async def ready():
        while not service.started:
            await asyncio.sleep(0.02)
        print(json.dumps({"port": listener.getsockname()[1]}), flush=True)

    async def run():
        announce = asyncio.create_task(ready())
        try:
            await service.serve(sockets=[listener])
        finally:
            announce.cancel()

    def watch_parent():
        while True:
            time.sleep(1)
            if os.getppid() != parent:
                os._exit(0)
    threading.Thread(target=watch_parent, daemon=True).start()
    asyncio.run(run())


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-check"]:
        import ssl
        import certifi
        import keyring
        import grpc
        from google.cloud import texttospeech
        context = ssl.create_default_context(cafile=certifi.where())
        assert context.cert_store_stats()["x509_ca"] > 0
        assert Path(os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"]).is_file()
        assert type(keyring.get_keyring()).__module__.startswith("keyring.backends.macOS")
        assert grpc.ssl_channel_credentials() is not None
        print(msg(
            "内置运行时、公共 CA 证书、gRPC、TTS 与 macOS 钥匙串后端可用。未访问用户凭据。",
            "Bundled runtime, public CA certs, gRPC, TTS, and macOS keyring backend are available. User credentials were not accessed.",
        ))
    else:
        main()
