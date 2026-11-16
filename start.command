#!/bin/bash
STUDIO_DIR="$(cd "$(dirname "$0")/studio" && pwd)" || exit 1
if [ -x "$STUDIO_DIR/.venv/bin/python" ]; then
  STUDIO_PYTHON="$STUDIO_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  STUDIO_PYTHON="$(command -v python3)"
else
  echo "未找到 Python。请先按 README 安装 Python 3.11 或更新版本与工坊依赖。"
  read -r -p "按回车关闭…"
  exit 1
fi
"$STUDIO_PYTHON" "$STUDIO_DIR/launch.py"
STUDIO_EXIT=$?
if [ "$STUDIO_EXIT" -ne 0 ]; then
  read -r -p "启动失败，按回车关闭…"
fi
exit "$STUDIO_EXIT"
