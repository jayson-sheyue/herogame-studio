"""Offline startup checks: no real services, browser windows or credentials."""

from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import launch


class LaunchTests(unittest.TestCase):
    def run_main(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            return launch.main()

    def test_probe_identifies_app_and_disables_proxy(self):
        page = BytesIO((launch.STUDIO / "static/index.html").read_bytes())
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=page)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with patch.object(launch.urllib.request, "build_opener", return_value=opener) as build:
            self.assertEqual(launch.probe(), "ready")
        self.assertEqual(build.call_args.args[0].proxies, {})
        opener.open.assert_called_once_with(launch.URL, timeout=1)

    def test_existing_service_opens_without_starting_or_stopping_process(self):
        with patch.object(launch, "probe", return_value="ready"), \
             patch.object(launch.subprocess, "Popen") as start, \
             patch.object(launch.webbrowser, "open", return_value=False) as browser:
            self.assertEqual(self.run_main(), 0)
        start.assert_not_called()
        browser.assert_called_once_with(launch.URL)

    def test_another_service_is_not_opened_or_stopped(self):
        with patch.object(launch, "probe", return_value="occupied"), \
             patch.object(launch.subprocess, "Popen") as start, \
             patch.object(launch.webbrowser, "open") as browser:
            self.assertEqual(self.run_main(), 1)
        start.assert_not_called()
        browser.assert_not_called()

    def test_new_service_opens_only_after_ready_and_waits_for_exit(self):
        process = Mock()
        process.poll.side_effect = [None, None, 0]
        process.wait.return_value = 0
        with patch.object(launch, "probe", side_effect=["unavailable", "unavailable", "ready"]), \
             patch.object(launch.subprocess, "Popen", return_value=process) as start, \
             patch.object(launch.webbrowser, "open") as browser, \
             patch.object(launch.time, "sleep"):
            self.assertEqual(self.run_main(), 0)
        command = start.call_args.args[0]
        self.assertEqual(command[:3], [launch.sys.executable, "-m", "uvicorn"])
        self.assertEqual(start.call_args.kwargs["cwd"], launch.STUDIO)
        browser.assert_called_once_with(launch.URL)
        process.wait.assert_called_once_with()
        process.terminate.assert_not_called()

    def test_failed_start_does_not_open_browser(self):
        process = Mock(returncode=1)
        process.poll.return_value = 1
        with patch.object(launch, "probe", return_value="unavailable"), \
             patch.object(launch.subprocess, "Popen", return_value=process), \
             patch.object(launch.webbrowser, "open") as browser:
            self.assertEqual(self.run_main(), 1)
        browser.assert_not_called()
        process.terminate.assert_not_called()

    def test_startup_timeout_cleans_up_owned_process(self):
        process = Mock()
        process.poll.return_value = None
        with patch.object(launch, "probe", return_value="unavailable"), \
             patch.object(launch.subprocess, "Popen", return_value=process), \
             patch.object(launch.webbrowser, "open") as browser, \
             patch.object(launch.time, "monotonic", side_effect=[0, 46]):
            self.assertEqual(self.run_main(), 1)
        browser.assert_not_called()
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=5)

    def test_ctrl_c_stops_owned_process(self):
        process = Mock()
        process.poll.return_value = None
        with patch.object(launch, "probe", side_effect=["unavailable", KeyboardInterrupt]), \
             patch.object(launch.subprocess, "Popen", return_value=process), \
             patch.object(launch.webbrowser, "open") as browser:
            self.assertEqual(self.run_main(), 0)
        browser.assert_not_called()
        process.terminate.assert_called_once_with()


@unittest.skipUnless(shutil.which("bash"), "macOS / POSIX launcher")
class CommandTests(unittest.TestCase):
    def test_double_click_prefers_venv_even_when_system_python_is_available(self):
        with tempfile.TemporaryDirectory(prefix="studio launch ") as folder:
            root = Path(folder)
            python = root / "studio/.venv/bin/python"
            python.parent.mkdir(parents=True)
            python.write_text('#!/bin/sh\nprintf "venv:%s\\n" "$1"\n')
            python.chmod(0o755)
            command = root / "start.command"
            shutil.copyfile(launch.STUDIO.parent / "start.command", command)
            result = subprocess.run(["bash", str(command)], cwd="/", capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), f"venv:{root}/studio/launch.py")


if __name__ == "__main__":
    unittest.main()
