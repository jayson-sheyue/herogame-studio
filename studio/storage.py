"""Small, atomic writes for project metadata; a failed save keeps the old file."""

import json
import os
from pathlib import Path
import tempfile


def write_json(path: Path, data: dict) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    write_bytes(path, text.encode("utf-8"))


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as stream:
            temp = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
