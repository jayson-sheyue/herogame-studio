"""Offline regressions. Never load the user's registry, settings or ADC."""

import asyncio
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

import project
from storage import write_json
import workspace_guard


class AtomicStorageTests(unittest.TestCase):
    def test_failed_replace_keeps_previous_file_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "工程" / "bible.json"
            write_json(path, {"prompt": "原来的提示词"})
            with patch("storage.os.replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    write_json(path, {"prompt": "new"})
            self.assertEqual(json.loads(path.read_text()), {"prompt": "原来的提示词"})
            self.assertEqual(list(path.parent.iterdir()), [path])
            write_json(path, {"prompt": "重试成功"})
            self.assertEqual(json.loads(path.read_text())["prompt"], "重试成功")


class StudioApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        old_root = project.paths.root
        self.addCleanup(project.paths.set_root, old_root)
        for name, value in {
            "REGISTRY_PATH": self.root / "registry.json",
            "IDLE_ROOT": self.root / "idle",
            "DEFAULT_ROOT": self.root / "idle",
        }.items():
            patcher = patch.object(project, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        project.paths.set_root(project.IDLE_ROOT)
        # Import only after replacing every boot-time data destination.
        import server

        self.server = server
        self.guard = workspace_guard.WorkspaceGuard()
        patcher = patch.object(workspace_guard, "workspace_guard", self.guard)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(server, "vertex_status", return_value={"project": "", "checks": {}})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://studio.test")
        self.addAsyncCleanup(self.client.aclose)
        self.token = self.guard.token

    async def post(self, path, data):
        response = await self.client.post(path, json=data, headers={"X-Studio-Workspace": self.token})
        self.token = response.headers.get("X-Studio-Workspace", self.token)
        return response

    async def open_project(self, name="工程 A", kind="herogame"):
        self.assertEqual((await self.post("/api/line", {"kind": kind})).status_code, 200)
        folder = self.root / name
        folder.mkdir(exist_ok=True)
        response = await self.post("/api/projects/use", {"folder": str(folder), "kind": kind})
        self.assertEqual(response.status_code, 200, response.text)
        return folder

    async def portrait(self):
        await self.open_project(kind="deskpet")
        bible = {
            "portrait_id": "sample", "appearance": "小狐狸", "gear": "围巾",
            "slots": [{"id": "turnaround", "frames": 4}, {"id": "idle", "frames": 2}, {"id": "walk", "frames": 2}],
            "prompts": {"idle": "before", "walk": "untouched"},
        }
        self.server.write_portrait_bible("sample", bible)
        response = await self.client.get("/api/portraits/sample")
        self.assertEqual(response.status_code, 200)
        return response.json()

    async def test_health_bootstraps_token_and_missing_or_stale_write_is_rejected(self):
        health = await self.client.get("/api/health")
        self.assertEqual(health.headers["X-Studio-Workspace"], self.token)
        missing = await self.client.post("/api/line", json={"kind": "deskpet"})
        self.assertEqual(missing.status_code, 409)
        stale = self.token
        await self.open_project()
        rejected = await self.client.post("/api/line/clear", json={}, headers={"X-Studio-Workspace": stale})
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(project.current_line(), "herogame")

    async def test_multipart_style_upload_reaches_endpoint_and_writes_real_draft(self):
        await self.open_project()
        image = Image.new("RGBA", (18, 18), (100, 80, 60, 255))
        stream = BytesIO()
        image.save(stream, format="PNG")
        response = await self.client.post(
            "/api/style/upload", headers={"X-Studio-Workspace": self.token},
            files={"file": ("sample.png", stream.getvalue(), "image/png")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(self.server.draft_style_png().is_file())
        with Image.open(self.server.draft_style_png()) as saved:
            self.assertEqual(saved.size, (18, 18))

    async def test_switch_during_inference_is_rejected_until_original_result_is_saved(self):
        original = await self.open_project()
        other = self.root / "工程 B"
        other.mkdir()
        entered, release = threading.Event(), threading.Event()

        def model(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test synchronization timed out")
            return json.dumps({"prompt": "sample", "visual_lock": "pixel"})

        with patch.object(self.server, "infer_json", model):
            task = asyncio.create_task(self.post("/api/style/infer", {"notes": "sample"}))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                for path, body in [
                    ("/api/projects/use", {"folder": str(other), "kind": "herogame"}),
                    ("/api/line", {"kind": "deskpet"}),
                    ("/api/line/clear", {}),
                    ("/api/projects/wipe", {"folder": str(other)}),
                ]:
                    self.assertEqual((await self.post(path, body)).status_code, 409, path)
                self.assertEqual((await self.client.get("/api/style")).status_code, 200)
            finally:
                release.set()
            self.assertEqual((await task).status_code, 200)
        self.assertTrue((original / "assets/studio/_style/bible.json").is_file())
        self.assertFalse((other / "assets").exists())
        for folder in [other, original, other]:
            response = await self.post("/api/projects/use", {"folder": str(folder), "kind": "herogame"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(project.paths.root, folder.resolve())

    async def test_failed_request_releases_workspace_and_resource(self):
        await self.open_project()
        with patch.object(self.server, "infer_json", side_effect=RuntimeError("offline fixture")):
            self.assertEqual((await self.post("/api/style/infer", {"notes": "sample"})).status_code, 502)
        self.assertEqual((await self.post("/api/line/clear", {})).status_code, 200)

    async def test_slow_voice_catalog_does_not_block_product_line_selection(self):
        import tts_client

        entered, release = threading.Event(), threading.Event()

        def voices(*args):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test synchronization timed out")
            return []

        with patch.object(self.server, "_tts", return_value=(voices, None, None)), patch.object(tts_client, "available_languages", return_value=[]):
            task = asyncio.create_task(self.client.get("/api/tts/voices"))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                self.assertEqual((await self.post("/api/line", {"kind": "deskpet"})).status_code, 200)
            finally:
                release.set()
            self.assertEqual((await task).status_code, 200)

    async def test_portrait_conflict_preserves_first_save_and_unedited_slot(self):
        portrait = await self.portrait()
        body = {"portrait_id": "sample", "expected_revision": portrait["revision"], "prompts": {"idle": "first edit"}}
        first = await self.post("/api/portraits/save", body)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["prompts"]["walk"], "untouched")
        second = await self.post("/api/portraits/save", {**body, "prompts": {"idle": "stale edit"}})
        self.assertEqual(second.status_code, 409)
        current = (await self.client.get("/api/portraits/sample")).json()
        self.assertEqual(current["prompts"]["idle"], "first edit")
        self.assertNotEqual(current["revision"], portrait["revision"])

    async def test_export_reports_partial_success_and_unknown_slot(self):
        await self.portrait()

        def export(pid, sid, **kwargs):
            if sid != "idle":
                raise FileNotFoundError(f"{sid}: no draft")
            return {"slot_id": sid, "count": 2, "dir": "fixture-export"}

        with patch.object(self.server, "export_portrait_slot", export):
            response = await self.post("/api/portraits/export", {"portrait_id": "sample"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["exports"][0]["count"], 2)
            self.assertEqual(len(response.json()["errors"]), 2)
            unknown = await self.post("/api/portraits/export", {"portrait_id": "sample", "slot_id": "unknown"})
            self.assertEqual(unknown.status_code, 400)

    async def test_failed_frame_export_preserves_previous_results_and_retry_writes_real_pngs(self):
        await self.portrait()
        import portrait_assets

        frames = portrait_assets.draft_portrait_frames_dir("sample", "idle")
        frames.mkdir(parents=True)
        image = Image.new("RGBA", (18, 18), (0, 255, 255, 255))
        image.putpixel((9, 9), (30, 30, 40, 255))
        for name in ["00.png", "01.png"]:
            image.save(frames / name)
        exported = portrait_assets.export_portrait_dir("sample", "idle")
        exported.mkdir(parents=True)
        (exported / "old.png").write_bytes(b"previous result")
        original_keyer = portrait_assets.cyan_key_png
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("disk full fixture")
            return original_keyer(*args, **kwargs)

        with patch.object(portrait_assets, "cyan_key_png", fail_second):
            failed = await self.post("/api/portraits/export", {"portrait_id": "sample", "slot_id": "idle"})
            self.assertEqual(failed.status_code, 400)
        self.assertEqual((exported / "old.png").read_bytes(), b"previous result")
        self.assertEqual(list(exported.iterdir()), [exported / "old.png"])
        retry = await self.post("/api/portraits/export", {"portrait_id": "sample", "slot_id": "idle"})
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["exports"][0]["count"], 2)
        self.assertFalse((exported / "old.png").exists())
        for path in exported.glob("*.png"):
            with Image.open(path) as result:
                self.assertEqual(result.getpixel((0, 0))[3], 0)
                self.assertEqual(result.getpixel((9, 9))[3], 255)


class WorkspaceLeaseTests(unittest.TestCase):
    def test_same_asset_conflicts_but_independent_assets_and_reads_remain_available(self):
        guard = workspace_guard.WorkspaceGuard()
        with guard.lease(token=guard.token, mutation=True, resource=("portrait_id", "a")):
            with self.assertRaisesRegex(Exception, "409"):
                with guard.lease(token=guard.token, mutation=True, resource=("portrait_id", "a")):
                    self.fail("same record must not run twice")
            with guard.lease(token=guard.token, mutation=True, resource=("portrait_id", "b")):
                pass
            with guard.lease(token=guard.token):
                pass
        with guard.lease(token=guard.token, switch=True, mutation=True):
            pass


if __name__ == "__main__":
    unittest.main()
