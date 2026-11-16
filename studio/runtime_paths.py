"""Keep desktop state outside the read-only application; retain source defaults."""

import os
from pathlib import Path


def data_root() -> Path:
    override = os.environ.get("STUDIO_DATA_DIR", "").strip()
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            raise ValueError("STUDIO_DATA_DIR 必须是绝对路径。")
        return path.resolve()
    return Path(__file__).resolve().parent
