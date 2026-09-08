#!/usr/bin/env python3
"""Generate and commit Lyria BGM for every stage missing bgm in stage.json."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bgm_client import generate_stage_bgm, load_stage_reference_png  # noqa: E402
from game_assets import game_stage_bgm, stage_manifest_path, upsert_stage_bgm  # noqa: E402
from project import paths  # noqa: E402


def main() -> None:
    stages_root = paths.game / "stages"
    pending = sorted(p for p in stages_root.glob("*/stage.json") if not json.loads(p.read_text()).get("bgm"))
    if not pending:
        print("All stages already have BGM.")
        return
    print(f"Packing BGM for {len(pending)} stage(s)…")
    for manifest_path in pending:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        stage_id = manifest["id"]
        display = manifest.get("displayName") or stage_id
        visual = manifest.get("visual") or display
        print(f"  · {display} ({stage_id})")
        ref = load_stage_reference_png(stage_id)
        try:
            mp3, _note, meta = generate_stage_bgm(
                display_name=display,
                visual=visual,
                bpm=int(manifest.get("bgmMeta", {}).get("bpm") or 118),
                image_bytes=ref[0] if ref else None,
                image_mime=ref[1] if ref else "image/png",
            )
        except Exception as exc:
            if ref and "content_blocked" in str(exc).lower():
                print(f"    ! image prompt blocked, retry text-only")
                mp3, _note, meta = generate_stage_bgm(
                    display_name=display,
                    visual=visual,
                    bpm=int(manifest.get("bgmMeta", {}).get("bpm") or 118),
                    image_bytes=None,
                )
            else:
                raise
        dest = game_stage_bgm(stage_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(mp3)
        upsert_stage_bgm(stage_id, meta)
        print(f"    → {dest} ({len(mp3)} bytes)")
        time.sleep(0.5)
    print("Done.")


if __name__ == "__main__":
    main()
