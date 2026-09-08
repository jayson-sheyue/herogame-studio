"""立绘/桌宠分区：独立于对战英雄管线的草稿、切分与去青导出。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from project import paths
from score import FRAME_SLOTS, cyan_key_png, looks_like_grid_2x2


def ensure_portrait_dirs() -> None:
    for path in (
        paths.studio / "portraits",
        paths.drafts / "portraits",
        paths.studio / "exports" / "portraits",
    ):
        path.mkdir(parents=True, exist_ok=True)


def portrait_bible_path(portrait_id: str) -> Path:
    return paths.studio / "portraits" / portrait_id / "bible.json"


def draft_portrait_png(portrait_id: str, slot_id: str) -> Path:
    return paths.drafts / "portraits" / portrait_id / f"{slot_id}.png"


def draft_portrait_source_png(portrait_id: str, slot_id: str) -> Path:
    return paths.drafts / "portraits" / portrait_id / f"{slot_id}.source.png"


def draft_portrait_frames_dir(portrait_id: str, slot_id: str) -> Path:
    return paths.drafts / "portraits" / portrait_id / "frames" / slot_id


def export_portrait_dir(portrait_id: str, slot_id: str | None = None) -> Path:
    base = paths.studio / "exports" / "portraits" / portrait_id
    return base / slot_id if slot_id else base


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_portrait_bible(portrait_id: str) -> dict:
    return _read_json(portrait_bible_path(portrait_id))


def write_portrait_bible(portrait_id: str, data: dict) -> None:
    ensure_portrait_dirs()
    _write_json(portrait_bible_path(portrait_id), data)


def list_portrait_ids() -> list[str]:
    root = paths.studio / "portraits"
    if not root.is_dir():
        return []
    out: list[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "bible.json").exists():
            out.append(child.name)
    return out


def delete_portrait(portrait_id: str) -> dict:
    """Remove bible, drafts, split frames, and cyan-key exports for one portrait."""
    pid = (portrait_id or "").strip()
    if not pid:
        raise ValueError("没有 portrait_id。")
    removed: list[str] = []
    for folder in (
        paths.studio / "portraits" / pid,
        paths.drafts / "portraits" / pid,
        paths.studio / "exports" / "portraits" / pid,
    ):
        if folder.exists() and folder.is_dir():
            shutil.rmtree(folder)
            removed.append(str(folder))
    return {"ok": True, "portrait_id": pid, "removed": removed}

def list_portrait_split_frames(portrait_id: str, slot_id: str) -> list[Path]:
    folder = draft_portrait_frames_dir(portrait_id, slot_id)
    if not folder.is_dir():
        return []
    return sorted(
        (p for p in folder.iterdir() if p.suffix.lower() == ".png" and p.stem.isdigit()),
        key=lambda p: int(p.stem),
    )


def clear_portrait_split_frames(portrait_id: str, slot_id: str) -> None:
    folder = draft_portrait_frames_dir(portrait_id, slot_id)
    if not folder.is_dir():
        return
    for item in folder.iterdir():
        if item.is_file():
            item.unlink()


def ensure_portrait_split_source(portrait_id: str, slot_id: str) -> Path | None:
    """Keep `.source.png` in sync with the current draft before cutting.

    Older builds only copied draft→source once; regenerating the draft left a
    stale source, so 切分/去青 kept punching the previous strip (e.g. hollow
    cream clothes) while the UI preview showed the new draft.
    """
    draft = draft_portrait_png(portrait_id, slot_id)
    if not draft.exists():
        return None
    source = draft_portrait_source_png(portrait_id, slot_id)
    source.parent.mkdir(parents=True, exist_ok=True)
    try:
        need_copy = (not source.exists()) or (source.stat().st_mtime_ns < draft.stat().st_mtime_ns)
    except OSError:
        need_copy = True
    if need_copy:
        shutil.copy2(draft, source)
    return source


def reset_portrait_slot_derivatives(portrait_id: str, slot_id: str) -> None:
    """Drop split frames, cyan exports, and frozen source after a new draft."""
    draft_portrait_source_png(portrait_id, slot_id).unlink(missing_ok=True)
    clear_portrait_split_frames(portrait_id, slot_id)
    clear_portrait_exports(portrait_id, slot_id)


def portrait_slot_frame_count(slot_id: str, bible: dict | None = None) -> int:
    from prompts import normalize_portrait_slot_list

    for slot in normalize_portrait_slot_list((bible or {}).get("slots"), fallback_all=True):
        if slot["id"] == slot_id:
            return int(slot.get("frames") or 5)
    return int(FRAME_SLOTS.get(slot_id) or 5)


def resolve_portrait_slots(bible: dict | None = None, *, fallback_all: bool = True) -> list[dict]:
    from prompts import normalize_portrait_slot_list

    return normalize_portrait_slot_list((bible or {}).get("slots"), fallback_all=fallback_all)


def split_portrait_strip(
    portrait_id: str,
    slot_id: str,
    *,
    frames: int | None = None,
    variant: int = 0,
    bible: dict | None = None,
) -> list[Path]:
    from game_assets import split_strip

    src = ensure_portrait_split_source(portrait_id, slot_id)
    if not src:
        raise FileNotFoundError("还没有图可切。先生成套图。")
    n = int(frames) if frames else portrait_slot_frame_count(slot_id, bible)
    if n < 2:
        raise ValueError("这一张不是分镜条，不用切。")
    variant = int(variant) % 8
    if n == 4:
        try:
            if looks_like_grid_2x2(Image.open(src)):
                variant = 5
        except Exception:  # noqa: BLE001
            variant = 5
    dest = draft_portrait_frames_dir(portrait_id, slot_id)
    clear_portrait_split_frames(portrait_id, slot_id)
    # Old transparent exports belong to the previous cut — drop so play bay
    # doesn't keep showing hollow/stale keyed frames next to the new split.
    clear_portrait_exports(portrait_id, slot_id)
    out = split_strip(src, dest, n, variant=variant)
    meta_path = dest / "cells.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(meta, dict):
                meta["split_frames"] = n
                meta["expected"] = n
                meta["source"] = "portrait"
                meta_path.write_text(json.dumps(meta), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    return out


def export_portrait_slot(
    portrait_id: str,
    slot_id: str,
    *,
    strict: bool = True,
    bible: dict | None = None,
) -> dict:
    """Cyan-key split frames into exports/portraits/<id>/<slot>/."""
    frames = list_portrait_split_frames(portrait_id, slot_id)
    if not frames:
        # Fall back: equal-width slice of draft strip
        draft = draft_portrait_png(portrait_id, slot_id)
        if not draft.exists():
            raise FileNotFoundError(f"槽位「{slot_id}」没有可导出的帧，请先生成并切分。")
        n = portrait_slot_frame_count(slot_id, bible)
        split_portrait_strip(portrait_id, slot_id, frames=n, variant=0, bible=bible)
        frames = list_portrait_split_frames(portrait_id, slot_id)
    if not frames:
        raise FileNotFoundError(f"槽位「{slot_id}」切分后仍无帧。")

    dest_dir = export_portrait_dir(portrait_id, slot_id)
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for src in frames:
        out = dest_dir / src.name
        keyed = cyan_key_png(src.read_bytes(), frames=1, strict=strict)
        out.write_bytes(keyed)
        written.append(str(out))
    return {
        "portrait_id": portrait_id,
        "slot_id": slot_id,
        "count": len(written),
        "dir": str(dest_dir),
        "files": written,
    }


def portrait_asset_view(portrait_id: str, slot_id: str, bible: dict | None = None) -> dict:
    draft = draft_portrait_png(portrait_id, slot_id)
    source = draft_portrait_source_png(portrait_id, slot_id)
    frames = list_portrait_split_frames(portrait_id, slot_id)
    export_dir = export_portrait_dir(portrait_id, slot_id)
    exports = []
    if export_dir.is_dir():
        exports = sorted(
            (p for p in export_dir.iterdir() if p.suffix.lower() == ".png" and p.stem.isdigit()),
            key=lambda p: int(p.stem),
        )
    n = portrait_slot_frame_count(slot_id, bible)
    draft_m = int(draft.stat().st_mtime_ns) if draft.exists() else 0
    # Stale vs the sheet that cut should use (source if present, else draft).
    cut_m = 0
    if source.exists():
        cut_m = int(source.stat().st_mtime_ns)
    elif draft.exists():
        cut_m = draft_m
    frames_stale = False
    if cut_m and frames:
        try:
            frames_stale = any(p.stat().st_mtime_ns < cut_m for p in frames)
        except OSError:
            frames_stale = True
    # Also stale if draft moved past frozen source (regen before re-split).
    if draft.exists() and source.exists():
        try:
            if draft.stat().st_mtime_ns > source.stat().st_mtime_ns:
                frames_stale = True if frames else frames_stale
        except OSError:
            pass
    exports_stale = False
    if exports and (draft_m or (frames and not frames_stale)):
        try:
            newest_src = draft_m
            if frames and not frames_stale:
                newest_src = max(newest_src, max(p.stat().st_mtime_ns for p in frames))
            exports_stale = any(p.stat().st_mtime_ns < newest_src for p in exports)
        except OSError:
            exports_stale = True
    return {
        "slot_id": slot_id,
        "has_draft": draft.exists(),
        "draft_mtime": draft_m,
        "frame_count": n,
        "split_count": len(frames),
        "export_count": len(exports),
        "frames_stale": frames_stale,
        "exports_stale": exports_stale,
        "draft_url": f"/drafts/portraits/{portrait_id}/{slot_id}.png?t={draft.stat().st_mtime_ns}" if draft.exists() else "",
        "frames": [
            f"/drafts/portraits/{portrait_id}/frames/{slot_id}/{p.name}?t={p.stat().st_mtime_ns}" for p in frames
        ],
        "exports": [
            f"/library/exports/portraits/{portrait_id}/{slot_id}/{p.name}?t={p.stat().st_mtime_ns}" for p in exports
        ],
        "export_dir": str(export_dir) if exports else "",
    }


def discard_portrait_slot(portrait_id: str, slot_id: str) -> dict:
    """Drop draft strip + split frames for one slot. Exports are left alone until user re-exports."""
    draft_portrait_png(portrait_id, slot_id).unlink(missing_ok=True)
    draft_portrait_source_png(portrait_id, slot_id).unlink(missing_ok=True)
    clear_portrait_split_frames(portrait_id, slot_id)
    bible = read_portrait_bible(portrait_id)
    return portrait_asset_view(portrait_id, slot_id, bible)


def clear_portrait_exports(portrait_id: str, slot_id: str) -> None:
    dest = export_portrait_dir(portrait_id, slot_id)
    if dest.exists():
        shutil.rmtree(dest)


def _portrait_body_guide(bible: dict | None) -> dict:
    from game_assets import DEFAULT_BODY_GUIDE_H, MAX_BODY_GUIDE_H, MIN_BODY_GUIDE_H

    raw = (bible or {}).get("body_guide_h")
    default = int(DEFAULT_BODY_GUIDE_H)
    if raw is None or raw == "":
        return {
            "guide_body_h": default,
            "default_body_guide_h": default,
            "guide_mode": "default",
            "visual_scale": 1.0,
        }
    try:
        guide = int(round(float(raw)))
    except (TypeError, ValueError):
        guide = default
    guide = max(MIN_BODY_GUIDE_H, min(MAX_BODY_GUIDE_H, guide))
    return {
        "guide_body_h": guide,
        "default_body_guide_h": default,
        "guide_mode": "custom" if guide != default else "default",
        "visual_scale": round(guide / float(default), 4),
    }


def set_portrait_body_guide(portrait_id: str, body_guide_h: int | float | None) -> dict:
    bible = read_portrait_bible(portrait_id) or {"portrait_id": portrait_id}
    if body_guide_h is None or body_guide_h == "":
        bible.pop("body_guide_h", None)
    else:
        from game_assets import MAX_BODY_GUIDE_H, MIN_BODY_GUIDE_H

        bible["body_guide_h"] = max(MIN_BODY_GUIDE_H, min(MAX_BODY_GUIDE_H, int(round(float(body_guide_h)))))
    write_portrait_bible(portrait_id, bible)
    return _portrait_body_guide(bible)


def ensure_portrait_equal_frames(portrait_id: str, slot_id: str, *, force: bool = False, bible: dict | None = None) -> list[Path]:
    """Equal-width slice of the draft strip into frames/ for body-scale review."""
    path = draft_portrait_png(portrait_id, slot_id)
    if not path.exists():
        raise FileNotFoundError(f"套图「{slot_id}」还没有草稿，请先生成。")
    n = portrait_slot_frame_count(slot_id, bible)
    existing = list_portrait_split_frames(portrait_id, slot_id)
    if existing and len(existing) == n and not force:
        try:
            newest = max(p.stat().st_mtime for p in existing)
            if newest >= path.stat().st_mtime - 0.05:
                return existing
        except OSError:
            pass
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    fw = max(1, w // max(1, n))
    dest = draft_portrait_frames_dir(portrait_id, slot_id)
    clear_portrait_split_frames(portrait_id, slot_id)
    dest.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for i in range(n):
        cell = im.crop((i * fw, 0, min(w, (i + 1) * fw), h))
        fp = dest / f"{i:02d}.png"
        cell.save(fp, format="PNG")
        out.append(fp)
    meta = {
        "variant": -1,
        "label": "草稿条等宽切分（身长校对）",
        "expected": n,
        "split_frames": n,
        "applied": True,
        "cells": [],
        "source": "portrait_body_scale",
    }
    (dest / "cells.json").write_text(json.dumps(meta), encoding="utf-8")
    return out


def measure_portrait_ref_body(portrait_id: str, ref_slot: str = "idle", bible: dict | None = None) -> dict:
    from game_assets import measure_strip_body

    bible = bible or read_portrait_bible(portrait_id)
    path = draft_portrait_png(portrait_id, ref_slot)
    if not path.exists():
        raise FileNotFoundError(f"缺少基准套图「{ref_slot}」，请先生成草稿（建议先出待机）。")
    n = portrait_slot_frame_count(ref_slot, bible)
    m = measure_strip_body(Image.open(path).convert("RGBA"), n)
    if not m.get("body_h"):
        raise ValueError(f"基准套图「{ref_slot}」测不到躯干身高。")
    guide = _portrait_body_guide(bible)
    idle_h = int(m["body_h"])
    return {
        "ref_slot": ref_slot,
        "ref_body_h": int(guide["guide_body_h"]),
        "idle_body_h": idle_h,
        "guide_body_h": int(guide["guide_body_h"]),
        "default_body_guide_h": int(guide["default_body_guide_h"]),
        "guide_mode": guide["guide_mode"],
        "visual_scale": guide["visual_scale"],
        "ref_feet_y": int(m["feet_y"]),
        "ref_frame_h": int(m["frame_h"]),
        "ref_frame_w": int(m.get("frame_w") or 0),
        "tol": 0.04,
    }


def portrait_body_scale_slots(bible: dict | None = None) -> list[dict]:
    """Motion slots eligible for body-scale (skip turnaround)."""
    slots = resolve_portrait_slots(bible, fallback_all=True)
    return [s for s in slots if s["id"] != "turnaround"]


_REF_SLOT_PRIORITY = ("idle", "walk", "happy", "sad", "sleep", "wave")


def resolve_portrait_ref_slot(
    portrait_id: str,
    bible: dict | None = None,
    *,
    preferred: str = "idle",
) -> str:
    """Pick a motion-slot draft to use as body-scale reference (idle if present, else first available)."""
    bible = bible or read_portrait_bible(portrait_id)
    plan_ids = [s["id"] for s in portrait_body_scale_slots(bible)]
    if not plan_ids:
        raise FileNotFoundError("套图清单里没有可校对的动作槽（三视图不算）。")
    candidates: list[str] = []
    pref = (preferred or "idle").strip()
    if pref in plan_ids:
        candidates.append(pref)
    for sid in _REF_SLOT_PRIORITY:
        if sid in plan_ids and sid not in candidates:
            candidates.append(sid)
    for sid in plan_ids:
        if sid not in candidates:
            candidates.append(sid)
    for sid in candidates:
        if draft_portrait_png(portrait_id, sid).exists():
            return sid
    titles = {s["id"]: s.get("title") or s["id"] for s in portrait_body_scale_slots(bible)}
    need = "、".join(titles.get(s, s) for s in plan_ids[:4])
    raise FileNotFoundError(
        f"还没有可作身长基准的动作草稿。请先生成至少一套动作条（例如 {need}）。"
    )


def list_portrait_body_scale_workspace(
    portrait_id: str,
    *,
    ref_slot: str = "idle",
    tol: float = 0.04,
) -> dict:
    from game_assets import measure_strip_body

    bible = read_portrait_bible(portrait_id)
    ref_slot = resolve_portrait_ref_slot(portrait_id, bible, preferred=ref_slot)
    ref = measure_portrait_ref_body(portrait_id, ref_slot, bible)
    target = int(ref["ref_body_h"])
    slots_out: list[dict] = []
    for slot in portrait_body_scale_slots(bible):
        sid = slot["id"]
        path = draft_portrait_png(portrait_id, sid)
        if not path.exists():
            continue
        n = portrait_slot_frame_count(sid, bible)
        m = measure_strip_body(Image.open(path).convert("RGBA"), n)
        body_h = int(m.get("body_h") or 0)
        delta = body_h - target
        ok = body_h > 0 and abs(delta) / max(1, target) <= tol
        slots_out.append(
            {
                "id": sid,
                "title": slot.get("title") or sid,
                "frames": n,
                "body_h": body_h,
                "delta": delta,
                "ok": ok,
                "is_ref": sid == ref_slot,
            }
        )
    return {
        "portrait_id": portrait_id,
        "kind": "portrait",
        **ref,
        "tol": tol,
        "slots": slots_out,
        "ok_count": sum(1 for s in slots_out if s["ok"]),
        "warn_count": sum(1 for s in slots_out if not s["ok"]),
    }


def describe_portrait_body_scale_slot(
    portrait_id: str,
    slot_id: str,
    *,
    ref_slot: str = "idle",
    tol: float = 0.04,
    ensure: bool = True,
    force: bool = False,
) -> dict:
    from game_assets import measure_cell_body
    from statistics import median

    bible = read_portrait_bible(portrait_id)
    ref_slot = resolve_portrait_ref_slot(portrait_id, bible, preferred=ref_slot)
    ref = measure_portrait_ref_body(portrait_id, ref_slot, bible)
    target = int(ref["ref_body_h"])
    if ensure:
        ensure_portrait_equal_frames(portrait_id, slot_id, force=force, bible=bible)
    files = list_portrait_split_frames(portrait_id, slot_id)
    if len(files) < 1:
        raise FileNotFoundError(f"套图「{slot_id}」没有可校对的帧。先切分或打开工作区自动切分。")
    title = next((s.get("title") for s in portrait_body_scale_slots(bible) if s["id"] == slot_id), slot_id)
    frames_out: list[dict] = []
    for i, fp in enumerate(files):
        cell = Image.open(fp).convert("RGBA")
        m = measure_cell_body(cell)
        body_h = int(m.get("body_h") or 0)
        delta = body_h - target
        ok = body_h > 0 and abs(delta) / max(1, target) <= tol
        frames_out.append(
            {
                "index": i,
                "body_h": body_h,
                "dense_h": int(m.get("dense_h") or 0),
                "ink_h": int(m.get("ink_h") or 0),
                "feet_y": int(m.get("feet_y") or 0),
                "head_y": int(m.get("head_y") or 0),
                "torso_w": int(m.get("torso_w") or 0),
                "delta": delta,
                "ok": ok,
                "ground_lift": 0,
                "width": cell.size[0],
                "height": cell.size[1],
                "url": f"/drafts/portraits/{portrait_id}/frames/{slot_id}/{fp.name}?t={fp.stat().st_mtime_ns}",
            }
        )
    body_hs = [f["body_h"] for f in frames_out if f["body_h"] > 0]
    slot_body = int(median(body_hs)) if body_hs else 0
    slot_delta = slot_body - target
    return {
        "portrait_id": portrait_id,
        "kind": "portrait",
        "slot_id": slot_id,
        "title": title or slot_id,
        "is_ref": slot_id == ref_slot,
        "air_acting": False,
        **ref,
        "tol": tol,
        "body_h": slot_body,
        "delta": slot_delta,
        "ok": slot_body > 0 and abs(slot_delta) / max(1, target) <= tol,
        "frames": frames_out,
        "asset": portrait_asset_view(portrait_id, slot_id, bible),
    }


def save_portrait_body_scale_slot(
    portrait_id: str,
    slot_id: str,
    scales: dict[int, float] | None = None,
    *,
    ref_slot: str = "idle",
    feet_dys: dict[int, int] | None = None,
    mirrors: dict[int, bool] | None = None,
    order: list[int] | None = None,
) -> dict:
    """Apply per-frame scales; rebuild draft strip + frames; cyan-key export that slot."""
    from game_assets import CYAN_FILL, measure_cell_body, measure_strip_body, place_cell_on_canvas, _plan_place_top

    bible = read_portrait_bible(portrait_id)
    ref_slot = resolve_portrait_ref_slot(portrait_id, bible, preferred=ref_slot)
    ref = measure_portrait_ref_body(portrait_id, ref_slot, bible)
    ensure_portrait_equal_frames(portrait_id, slot_id, bible=bible)
    files = list_portrait_split_frames(portrait_id, slot_id)
    if len(files) < 1:
        raise FileNotFoundError(f"套图「{slot_id}」没有可保存的帧。")
    n_src = len(files)
    if order is None:
        perm = list(range(n_src))
    else:
        perm = [int(x) for x in order]
        if not perm:
            raise ValueError("播放序列不能为空。")
        if len(perm) > 24:
            raise ValueError("播放序列过长（最多 24 帧）。")
        for src_i in perm:
            if src_i < 0 or src_i >= n_src:
                raise ValueError(f"帧索引越界：{src_i}")
    scale_map = {int(k): float(v) for k, v in (scales or {}).items()}
    dy_map = {int(k): int(v) for k, v in (feet_dys or {}).items()}
    mirror_map = {int(k): bool(v) for k, v in (mirrors or {}).items()}
    target_feet = int(ref["ref_feet_y"])
    target_fh = int(ref["ref_frame_h"])
    min_fw = max(64, int(ref.get("ref_frame_w") or 64))

    src_cells = [Image.open(files[src_i]).convert("RGBA") for src_i in perm]
    planned: list[dict] = []
    for new_i, cell in enumerate(src_cells):
        scale = scale_map.get(new_i, 1.0)
        user_dy = int(dy_map.get(new_i, 0))
        mirror = bool(mirror_map.get(new_i, False))
        plan_cell = cell.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if mirror else cell
        planned.append(
            {
                "cell": cell,
                "scale": scale,
                "feet_dy": user_dy,
                "user_dy": user_dy,
                "mirror": mirror,
                "top": _plan_place_top(plan_cell, scale=scale, target_feet_y=target_feet, feet_dy=user_dy),
            }
        )
    y_shift = max(0, max((-int(p["top"]) for p in planned), default=0))

    rebuilt: list[Image.Image] = []
    applied: list[dict] = []
    for new_i, plan in enumerate(planned):
        cell = plan["cell"]
        before = measure_cell_body(cell)
        placed = place_cell_on_canvas(
            cell,
            scale=plan["scale"],
            target_feet_y=target_feet,
            target_frame_h=target_fh,
            min_frame_w=min_fw,
            feet_dy=plan["feet_dy"],
            y_shift=y_shift,
            mirror=plan["mirror"],
        )
        after = measure_cell_body(placed)
        rebuilt.append(placed)
        applied.append(
            {
                "index": new_i,
                "source_index": int(perm[new_i]),
                "scale": round(float(plan["scale"]), 4),
                "feet_dy": plan["feet_dy"],
                "auto_lift": 0,
                "user_feet_dy": plan["user_dy"],
                "mirror": plan["mirror"],
                "y_shift": y_shift,
                "before": int(before.get("body_h") or 0),
                "after": int(after.get("body_h") or 0),
            }
        )

    dest_dir = draft_portrait_frames_dir(portrait_id, slot_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_paths: list[Path] = []
    for i, placed in enumerate(rebuilt):
        tmp = dest_dir / f".body_scale_tmp_{i:02d}.png"
        placed.save(tmp, format="PNG")
        tmp_paths.append(tmp)
    for old in files:
        try:
            old.unlink()
        except OSError:
            pass
    for i, tmp in enumerate(tmp_paths):
        tmp.replace(dest_dir / f"{i:02d}.png")

    fw = max(im.size[0] for im in rebuilt)
    fh = max(im.size[1] for im in rebuilt)
    sheet = Image.new("RGBA", (fw * len(rebuilt), fh), CYAN_FILL)
    for i, im in enumerate(rebuilt):
        cell_canvas = Image.new("RGBA", (fw, fh), CYAN_FILL)
        cell_canvas.paste(im, ((fw - im.size[0]) // 2, 0), im)
        sheet.paste(cell_canvas, (i * fw, 0))

    draft = draft_portrait_png(portrait_id, slot_id)
    draft.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(draft, format="PNG")
    src = draft_portrait_source_png(portrait_id, slot_id)
    sheet.save(src, format="PNG")

    # Persist frame count into bible slot meta if present
    slots = resolve_portrait_slots(bible, fallback_all=True)
    for s in slots:
        if s["id"] == slot_id:
            s["frames"] = len(rebuilt)
    bible["slots"] = slots
    write_portrait_bible(portrait_id, bible)

    meta_path = dest_dir / "cells.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        if not isinstance(meta, dict):
            meta = {}
    except Exception:  # noqa: BLE001
        meta = {}
    meta["split_frames"] = len(rebuilt)
    meta["expected"] = len(rebuilt)
    meta["applied"] = True
    meta["source"] = "portrait_body_scale"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    # Mirror hero body-scale save: write transparent frames immediately so the
    # user doesn't have to bounce back to the board and click 去青导出 per slot.
    export_info = export_portrait_slot(portrait_id, slot_id, strict=True, bible=bible)
    after_strip = measure_strip_body(sheet, len(rebuilt))
    return {
        "portrait_id": portrait_id,
        "slot_id": slot_id,
        "ref_slot": ref_slot,
        "ref_body_h": int(ref["ref_body_h"]),
        "order": perm,
        "dropped_sources": sorted(set(range(n_src)) - set(perm)),
        "frames_applied": applied,
        "body_h": int(after_strip.get("body_h") or 0),
        "delta": int(after_strip.get("body_h") or 0) - int(ref["ref_body_h"]),
        "frame_count": len(rebuilt),
        "exports_cleared": False,
        "exported": True,
        "export_count": int(export_info.get("count") or 0),
        "export_dir": str(export_info.get("dir") or ""),
        "asset": portrait_asset_view(portrait_id, slot_id, bible),
    }


def unify_portrait_body_scale(portrait_id: str, *, ref_slot: str = "idle") -> dict:
    """NEAREST-scale each motion draft strip to match guide body height from ref slot."""
    from game_assets import CYAN_FILL, measure_strip_body, place_cell_on_canvas

    bible = read_portrait_bible(portrait_id)
    ref_slot = resolve_portrait_ref_slot(portrait_id, bible, preferred=ref_slot)
    ref = measure_portrait_ref_body(portrait_id, ref_slot, bible)
    target = int(ref["ref_body_h"])
    target_feet = int(ref["ref_feet_y"])
    target_fh = int(ref["ref_frame_h"])
    min_fw = max(64, int(ref.get("ref_frame_w") or 64))
    updated: list[dict] = []
    for slot in portrait_body_scale_slots(bible):
        sid = slot["id"]
        if sid == ref_slot:
            continue
        path = draft_portrait_png(portrait_id, sid)
        if not path.exists():
            continue
        ensure_portrait_equal_frames(portrait_id, sid, force=True, bible=bible)
        files = list_portrait_split_frames(portrait_id, sid)
        if not files:
            continue
        cells = [Image.open(fp).convert("RGBA") for fp in files]
        strip_m = measure_strip_body(Image.open(path).convert("RGBA"), len(cells))
        body_h = int(strip_m.get("body_h") or 0)
        if body_h < 1:
            continue
        scale = target / float(body_h)
        scale = max(0.35, min(3.0, scale))
        rebuilt = [
            place_cell_on_canvas(
                cell,
                scale=scale,
                target_feet_y=target_feet,
                target_frame_h=target_fh,
                min_frame_w=min_fw,
            )
            for cell in cells
        ]
        dest_dir = draft_portrait_frames_dir(portrait_id, sid)
        clear_portrait_split_frames(portrait_id, sid)
        dest_dir.mkdir(parents=True, exist_ok=True)
        for i, placed in enumerate(rebuilt):
            placed.save(dest_dir / f"{i:02d}.png", format="PNG")
        fw = max(im.size[0] for im in rebuilt)
        fh = max(im.size[1] for im in rebuilt)
        sheet = Image.new("RGBA", (fw * len(rebuilt), fh), CYAN_FILL)
        for i, im in enumerate(rebuilt):
            cell_canvas = Image.new("RGBA", (fw, fh), CYAN_FILL)
            cell_canvas.paste(im, ((fw - im.size[0]) // 2, 0), im)
            sheet.paste(cell_canvas, (i * fw, 0))
        sheet.save(path, format="PNG")
        sheet.save(draft_portrait_source_png(portrait_id, sid), format="PNG")
        try:
            export_info = export_portrait_slot(portrait_id, sid, strict=True, bible=bible)
            exported = int(export_info.get("count") or 0)
        except FileNotFoundError:
            clear_portrait_exports(portrait_id, sid)
            exported = 0
        after = measure_strip_body(sheet, len(rebuilt))
        updated.append(
            {
                "slot_id": sid,
                "scale": round(scale, 4),
                "before": body_h,
                "after": int(after.get("body_h") or 0),
                "export_count": exported,
            }
        )
    return {
        "portrait_id": portrait_id,
        "ref_slot": ref_slot,
        "ref_body_h": target,
        "updated": updated,
        "count": len(updated),
        "exported": True,
    }

