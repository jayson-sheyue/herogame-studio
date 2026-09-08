"""Export committed heroes/stages as a zip the fighting game can import.

Studio still writes into the *open project's* assets/game (its own content
folder). Packs are how that content moves to a separate game install.
"""

from __future__ import annotations

import json
import re
import time
import zipfile
from io import BytesIO
from pathlib import Path

from project import paths

PACK_FORMAT = "herogame-pack"
PACK_VERSION = 1
SKIP_DIR_NAMES = {"_bak", "__pycache__"}
SKIP_FILE_NAMES = {".ds_store", "thumbs.db"}


def _safe_id(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "_", (value or "").strip())[:80]
    return text.strip("._") or ""


def _iter_pack_files(root: Path) -> list[Path]:
    out: list[Path] = []
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in SKIP_DIR_NAMES for part in rel_parts):
            continue
        if path.name.lower() in SKIP_FILE_NAMES:
            continue
        out.append(path)
    return out


def _hero_meta(hero_id: str) -> dict | None:
    folder = paths.game / "heroes" / hero_id
    manifest = folder / "fighter.json"
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {
        "id": hero_id,
        "displayName": str(data.get("displayName") or hero_id),
        "files": len(_iter_pack_files(folder)),
    }


def _stage_meta(stage_id: str) -> dict | None:
    folder = paths.game / "stages" / stage_id
    manifest = folder / "stage.json"
    png = folder / "stage.png"
    if not manifest.is_file() or not png.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {
        "id": stage_id,
        "displayName": str(data.get("displayName") or stage_id),
        "files": len(_iter_pack_files(folder)),
    }


def list_committed_ids() -> tuple[list[str], list[str]]:
    heroes: list[str] = []
    hero_root = paths.game / "heroes"
    if hero_root.is_dir():
        for folder in sorted(hero_root.iterdir()):
            if folder.is_dir() and (folder / "fighter.json").is_file():
                heroes.append(folder.name)
    stages: list[str] = []
    stage_root = paths.game / "stages"
    if stage_root.is_dir():
        for folder in sorted(stage_root.iterdir()):
            if folder.is_dir() and (folder / "stage.json").is_file() and (folder / "stage.png").is_file():
                stages.append(folder.name)
    return heroes, stages


def build_pack_zip(
    *,
    hero_ids: list[str] | None = None,
    stage_ids: list[str] | None = None,
) -> tuple[bytes, str, dict]:
    """Build a .zip pack from committed folders in the open studio project."""
    all_heroes, all_stages = list_committed_ids()
    if hero_ids is None and stage_ids is None:
        pick_heroes, pick_stages = all_heroes, all_stages
    else:
        pick_heroes = [_safe_id(x) for x in (hero_ids or []) if _safe_id(x)]
        pick_stages = [_safe_id(x) for x in (stage_ids or []) if _safe_id(x)]

    heroes_meta: list[dict] = []
    stages_meta: list[dict] = []
    missing: list[str] = []
    for hid in pick_heroes:
        meta = _hero_meta(hid)
        if not meta:
            missing.append(f"英雄 {hid} 还没有入库（缺 fighter.json）")
            continue
        heroes_meta.append(meta)
    for sid in pick_stages:
        meta = _stage_meta(sid)
        if not meta:
            missing.append(f"地图 {sid} 还没有入库（缺 stage.json / stage.png）")
            continue
        stages_meta.append(meta)
    if missing:
        raise ValueError("；".join(missing))
    if not heroes_meta and not stages_meta:
        raise ValueError("没有可导出的已入库英雄或地图。请先在工坊点「采用入库」。")

    pack = {
        "format": PACK_FORMAT,
        "version": PACK_VERSION,
        "exportedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "heroes": [{"id": h["id"], "displayName": h["displayName"]} for h in heroes_meta],
        "stages": [{"id": s["id"], "displayName": s["displayName"]} for s in stages_meta],
    }
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("pack.json", json.dumps(pack, ensure_ascii=False, indent=2))
        for h in heroes_meta:
            root = paths.game / "heroes" / h["id"]
            for path in _iter_pack_files(root):
                zf.write(path, arcname=f"heroes/{h['id']}/{path.relative_to(root).as_posix()}")
        for s in stages_meta:
            root = paths.game / "stages" / s["id"]
            for path in _iter_pack_files(root):
                zf.write(path, arcname=f"stages/{s['id']}/{path.relative_to(root).as_posix()}")

    names: list[str] = [h["id"] for h in heroes_meta] + [s["id"] for s in stages_meta]
    label = names[0] if len(names) == 1 else f"{len(names)}items"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"{label}.{stamp}.hgpk.zip"
    return buf.getvalue(), filename, pack
