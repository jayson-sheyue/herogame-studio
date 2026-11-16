#!/usr/bin/env python3
"""Run the studio's offline checks with the currently selected Python."""

from pathlib import Path
import shutil
import subprocess
import sys


def main() -> int:
    studio = Path(__file__).resolve().parents[1]
    node = shutil.which("node")
    if not node:
        print("开发检查需要 Node.js 18 或更新版本。正常运行工坊不需要 Node.js。", file=sys.stderr)
        return 1
    commands = [
        [sys.executable, "-m", "compileall", "-q", str(studio)],
        [sys.executable, "-m", "unittest", "discover", "-s", str(studio), "-v"],
        [node, "--check", str(studio / "static" / "app.js")],
        [node, "--test", str(studio / "test_frontend.cjs")],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=studio.parent, check=False)
        if result.returncode:
            return result.returncode
    print("离线检查通过。未执行真实 Vertex API 调用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
