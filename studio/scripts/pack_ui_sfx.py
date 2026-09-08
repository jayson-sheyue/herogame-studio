#!/usr/bin/env python3
"""Write procedural UI SFX into assets/game/ui/sfx/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from project import paths  # noqa: E402
from sfx_client import write_ui_sfx  # noqa: E402


def main() -> None:
    out = paths.game / "ui" / "sfx"
    files = write_ui_sfx(out)
    manifest = {
        "version": 1,
        "files": files,
    }
    (paths.game / "ui" / "sfx.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(files)} UI SFX → {out}")


if __name__ == "__main__":
    main()
