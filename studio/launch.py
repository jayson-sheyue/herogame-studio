"""Start the local studio, opening its page only after it is ready."""

import http.client
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

STUDIO = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8787/"


def probe() -> str:
    # Local requests should not be sent through a machine's network proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(URL, timeout=1) as response:
            page = response.read(65536)
            if "<title>英灵大乱斗 · 作图工坊</title>".encode() in page and b'id="lineGate"' in page:
                return "ready"
            return "occupied"
    except urllib.error.HTTPError:
        return "occupied"
    except (OSError, urllib.error.URLError, http.client.HTTPException):
        return "unavailable"


def open_studio() -> None:
    print(f"工坊已就绪：{URL}", flush=True)
    if not webbrowser.open(URL):
        print("浏览器未自动打开，请复制上面的地址。", flush=True)


def main() -> int:
    status = probe()
    if status == "ready":
        print("工坊已经在运行，正在打开已有服务。", flush=True)
        open_studio()
        return 0
    if status == "occupied":
        print("端口 8787 已被其他服务占用。请关闭占用服务后重试。", file=sys.stderr)
        return 1
    if sys.version_info < (3, 11):
        print("工坊需要 Python 3.11 或更新版本。", file=sys.stderr)
        return 1

    print("正在启动作图工坊… 保持此终端开启，按 Ctrl+C 停止。", flush=True)
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8787"],
        cwd=STUDIO,
    )
    try:
        deadline = time.monotonic() + 45
        while process.poll() is None:
            if probe() == "ready":
                open_studio()
                return process.wait()
            if time.monotonic() >= deadline:
                print("启动超时。请查看上面的错误，并按 README 检查依赖安装。", file=sys.stderr)
                return 1
            time.sleep(0.25)
        print("工坊启动失败。请查看上面的错误，并在虚拟环境中安装 requirements.txt。", file=sys.stderr)
        return process.returncode or 1
    except KeyboardInterrupt:
        print("\n正在停止工坊…", flush=True)
        return 0
    finally:
        # Only stop the process started here; an existing service is never stopped.
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
