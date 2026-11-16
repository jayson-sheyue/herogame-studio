"""Desktop transport and writable-path boundaries; no user data or live APIs."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import httpx
from starlette.responses import JSONResponse
from runtime_paths import data_root

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.backend import DesktopAccess


class DesktopPathsTests(unittest.TestCase):
    def test_source_keeps_existing_paths_and_desktop_override_is_absolute(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(data_root(), Path(__file__).resolve().parent)
        with patch.dict(os.environ, {"STUDIO_DATA_DIR":"/private/tmp/桌面测试 工程"}):
            self.assertEqual(data_root(), Path("/private/tmp/桌面测试 工程"))
        with patch.dict(os.environ, {"STUDIO_DATA_DIR":"relative/path"}):
            with self.assertRaises(ValueError): data_root()


class DesktopAccessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        async def inner(scope, receive, send):
            await JSONResponse({"ok": True})(scope, receive, send)
        self.token = "test-session-" + "0" * 40
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=DesktopAccess(inner, self.token)), base_url="http://127.0.0.1:18787")
        self.addAsyncCleanup(self.client.aclose)

    async def test_private_session_requires_bootstrap_and_cookie_is_http_only(self):
        self.assertEqual((await self.client.get("/api/health")).status_code, 403)
        self.assertEqual((await self.client.get("/_desktop/start?token=wrong")).status_code, 403)
        response = await self.client.get("/_desktop/start", params={"token":self.token})
        self.assertEqual(response.status_code, 303)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=strict", response.headers["set-cookie"])
        self.assertEqual((await self.client.get("/api/health")).json(), {"ok":True})

    async def test_foreign_origin_and_dns_rebinding_are_rejected(self):
        await self.client.get("/_desktop/start", params={"token":self.token})
        self.assertEqual((await self.client.post("/api/settings", headers={"Origin":"https://foreign.invalid"})).status_code, 403)
        self.assertEqual((await self.client.get("/", headers={"Host":"foreign.invalid:18787"})).status_code, 403)
        self.assertEqual((await self.client.post("/api/settings", headers={"Origin":"http://127.0.0.1:18787"})).status_code, 200)
