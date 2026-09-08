"""Committed game asset layout. Drafts never live here."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from statistics import median

from PIL import Image, ImageDraw, ImageFont

from combat import attach_fx_meta, move_id_from_fx_slot, sync_moves_into_fighter
from score import (
    AIR_SLOTS,
    CYAN_FILL,
    FRAME_SLOTS,
    SPLIT_VARIANT_COUNT,
    SPLIT_VARIANT_LABELS,
    air_ground_lifts,
    air_lifts_from_cells,
    cyan_key_image,
    looks_like_grid_2x2,
    measure_cell_body,
    measure_strip_body,
    pack_uniform_strip,
    rescale_strip_to_body,
    scrub_panel_borders,
    ink_bbox,
    _is_sheet_bg,
)
from project import paths

ROOT = Path(__file__).resolve().parent

CG_FILES = {
    "opening_cg": "cg/opening.png",
    "defeat_cg": "cg/defeat.png",
    "win_cg": "cg/win.png",
}

CG_KEYS = {
    "opening_cg": "opening",
    "defeat_cg": "defeat",
    "win_cg": "win",
}

SLOT_ALIASES = {
    "combo_up": ("combo_up", "combo"),
}

SELECT_PORTRAIT_SIZE = 128


def ensure_dirs() -> None:
    paths.ensure()


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def hero_rel(slot_id: str) -> str:
    move_id = move_id_from_fx_slot(slot_id)
    if move_id:
        return f"fx/{move_id}.png"
    return f"{slot_id}.png"


def draft_hero_png(hero_id: str, slot_id: str) -> Path:
    return paths.drafts / "heroes" / hero_id / f"{slot_id}.png"


def source_hero_png(hero_id: str, slot_id: str) -> Path:
    return paths.drafts / "heroes" / hero_id / f"{slot_id}.source.png"


def ensure_split_source(hero_id: str, slot_id: str) -> Path | None:
    source = source_hero_png(hero_id, slot_id)
    if source.exists():
        return source
    draft = draft_hero_png(hero_id, slot_id)
    src = draft if draft.exists() else committed_hero_png(hero_id, slot_id)
    if not src:
        return None
    source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, source)
    return source


def remember_split_source(hero_id: str, slot_id: str, src: Path) -> None:
    source = source_hero_png(hero_id, slot_id)
    source.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() != source.resolve():
        shutil.copy2(src, source)


def next_split_variant(hero_id: str, slot_id: str) -> int:
    data = load_split_layout(hero_id, slot_id)
    if not data:
        return 0
    return (int(data.get("variant") or 0) + 1) % SPLIT_VARIANT_COUNT


def draft_hero_frames_dir(hero_id: str, slot_id: str) -> Path:
    return paths.drafts / "heroes" / hero_id / "frames" / slot_id


def load_split_layout(hero_id: str, slot_id: str) -> dict | None:
    path = draft_hero_frames_dir(hero_id, slot_id) / "cells.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None
    # Body-scale writes cells:[] but still needs split_frames/expected for later cuts.
    if not data.get("cells") and data.get("split_frames") is None and data.get("expected") is None:
        return None
    return data


def _cells_frame_count(hero_id: str, slot_id: str) -> int | None:
    path = draft_hero_frames_dir(hero_id, slot_id) / "cells.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None
    for key in ("split_frames", "expected"):
        if data.get(key) is None:
            continue
        try:
            n = int(data.get(key))
        except (TypeError, ValueError):
            continue
        if n >= 1:
            return n
    return None


def _strip_implied_frames(path: Path | None, frame_w: int) -> int | None:
    if not path or not path.exists() or frame_w <= 0:
        return None
    try:
        w = Image.open(path).size[0]
    except OSError:
        return None
    if w < frame_w:
        return None
    if w % frame_w == 0:
        return max(1, w // frame_w)
    # Near-equal cells after pack: tolerate a few px of remainder.
    n = max(1, round(w / frame_w))
    if abs(w - n * frame_w) <= max(2, frame_w // 40):
        return n
    return None


def list_split_frames(hero_id: str, slot_id: str) -> list[Path]:
    folder = draft_hero_frames_dir(hero_id, slot_id)
    if not folder.is_dir():
        return []
    return sorted(
        (p for p in folder.iterdir() if p.suffix.lower() == ".png" and p.stem.isdigit()),
        key=lambda p: int(p.stem),
    )


def clear_split_frames(hero_id: str, slot_id: str) -> None:
    folder = draft_hero_frames_dir(hero_id, slot_id)
    if not folder.is_dir():
        return
    for item in folder.iterdir():
        if item.is_file():
            item.unlink()
    try:
        folder.rmdir()
        parent = folder.parent
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass


def split_strip(src: Path, dest_dir: Path, frames: int, variant: int = 0) -> list[Path]:
    frames = max(1, int(frames))
    raw = Image.open(src).convert("RGBA")
    # 2×2 宫格不能按「单行等宽缝」擦黑框，否则会切穿画面中央。
    # 单行四帧（三视图）不是宫格：不要改成 variant 5，否则 pack 会报「看不出 2×2」。
    if frames == 4 and looks_like_grid_2x2(raw):
        im = scrub_panel_borders(raw, frames=1)
        variant = 5
    else:
        im = scrub_panel_borders(raw, frames=frames)
        if int(variant or 0) % SPLIT_VARIANT_COUNT == 5:
            variant = 2
    width, height = im.size
    if width < 2 or height < 2:
        raise ValueError("图片太小，切不了。")
    _sheet, frame_ims, layout = pack_uniform_strip(im, frames, variant=variant)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for old in dest_dir.glob("*.png"):
        old.unlink()
    meta = dest_dir / "cells.json"
    if meta.exists():
        meta.unlink()
    if len(frame_ims) < 2:
        raise ValueError("没有切出有效的帧。")
    out: list[Path] = []
    for i, frame in enumerate(frame_ims):
        path = dest_dir / f"{i:02d}.png"
        frame.save(path, "PNG")
        out.append(path)
    layout["applied"] = False
    meta.write_text(json.dumps(layout), encoding="utf-8")
    return out


def mark_split_applied(hero_id: str, slot_id: str) -> None:
    path = draft_hero_frames_dir(hero_id, slot_id) / "cells.json"
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return
    if not isinstance(data, dict):
        return
    data["applied"] = True
    path.write_text(json.dumps(data), encoding="utf-8")


def assemble_split_sheet(hero_id: str, slot_id: str) -> Image.Image:
    files = list_split_frames(hero_id, slot_id)
    if len(files) < 2:
        raise ValueError("还没有切分预览。请先切分并播放确认。")
    ims = [Image.open(path).convert("RGBA") for path in files]
    fw = max(im.size[0] for im in ims)
    fh = max(im.size[1] for im in ims)
    sheet = Image.new("RGBA", (fw * len(ims), fh), CYAN_FILL)
    for i, im in enumerate(ims):
        x = i * fw + (fw - im.size[0]) // 2
        y = (fh - im.size[1]) // 2
        sheet.paste(im, (x, y), im)
    return sheet


def prepare_sprite_sheet(src: Path, frames: int, variant: int = 0) -> Image.Image:
    """Rebuild a strip so every cell is as wide as the widest pose (lying down, full extension, etc.)."""
    im = Image.open(src).convert("RGBA")
    frames = max(1, int(frames))
    if frames <= 1:
        return im
    im = scrub_panel_borders(im, frames=frames)
    sheet, _, _ = pack_uniform_strip(im, frames, variant=variant)
    return sheet


def draft_voice_mp3(hero_id: str, line_id: str) -> Path:
    return paths.drafts / "heroes" / hero_id / "voice" / f"{line_id}.mp3"


def draft_clone_audio(hero_id: str, kind: str) -> Path:
    return paths.drafts / "heroes" / hero_id / "voice" / f"clone_{kind}.wav"


def game_voice_mp3(hero_id: str, line_id: str) -> Path:
    return paths.game / "heroes" / hero_id / "voice" / f"{line_id}.mp3"


def committed_voice_mp3(hero_id: str, line_id: str) -> Path | None:
    return first_existing(
        game_voice_mp3(hero_id, line_id),
        paths.studio / hero_id / "voice" / f"{line_id}.mp3",
    )


def draft_style_png() -> Path:
    return paths.drafts / "style" / "style.png"


def draft_stage_png(stage_id: str) -> Path:
    return paths.drafts / "stages" / stage_id / "stage.png"


def draft_stage_bgm(stage_id: str) -> Path:
    return paths.drafts / "stages" / stage_id / "bgm.mp3"


def game_stage_bgm(stage_id: str) -> Path:
    return paths.game / "stages" / stage_id / "bgm.mp3"


def committed_stage_bgm(stage_id: str) -> Path | None:
    return first_existing(
        game_stage_bgm(stage_id),
        paths.studio / "stages" / stage_id / "bgm.mp3",
    )


def game_hero_png(hero_id: str, slot_id: str) -> Path:
    return paths.game / "heroes" / hero_id / hero_rel(slot_id)


def game_hero_select_png(hero_id: str) -> Path:
    return paths.game / "heroes" / hero_id / "select.png"


def game_style_png() -> Path:
    return paths.game / "style" / "style.png"


def game_stage_png(stage_id: str) -> Path:
    return paths.game / "stages" / stage_id / "stage.png"


def fighter_path(hero_id: str) -> Path:
    return paths.game / "heroes" / hero_id / "fighter.json"


def stage_manifest_path(stage_id: str) -> Path:
    return paths.game / "stages" / stage_id / "stage.json"


def index_path() -> Path:
    return paths.game / "index.json"


def first_existing(*paths: Path | None) -> Path | None:
    for path in paths:
        if path is not None and path.exists():
            return path
    return None


def committed_hero_png(hero_id: str, slot_id: str) -> Path | None:
    move_id = move_id_from_fx_slot(slot_id)
    if move_id:
        return first_existing(
            game_hero_png(hero_id, slot_id),
            paths.studio / hero_id / f"fx_{move_id}.png",
            paths.studio / hero_id / f"fx/{move_id}.png",
        )
    names = SLOT_ALIASES.get(slot_id, (slot_id,))
    found: list[Path | None] = []
    for name in names:
        found.append(paths.game / "heroes" / hero_id / f"{name}.png")
        found.append(paths.studio / hero_id / f"{name}.png")
    legacy = CG_FILES.get(slot_id)
    if legacy:
        found.append(paths.game / "heroes" / hero_id / legacy)
        found.append(paths.studio / hero_id / legacy)
    return first_existing(*found)


def committed_style_png() -> Path | None:
    return first_existing(game_style_png(), paths.studio / "_style" / "style.png")


def committed_stage_png(stage_id: str) -> Path | None:
    return first_existing(
        game_stage_png(stage_id),
        paths.studio / "stages" / stage_id / "stage.png",
    )


def work_hero_png(hero_id: str, slot_id: str) -> Path | None:
    names = SLOT_ALIASES.get(slot_id, (slot_id,))
    drafts = [draft_hero_png(hero_id, name) for name in names]
    return first_existing(*drafts, committed_hero_png(hero_id, slot_id))


def sprite_meta(png: Path, slot_id: str, keyed: bool, frames: int | None = None) -> dict:
    im = Image.open(png)
    w, h = im.size
    n = int(frames) if frames is not None else FRAME_SLOTS.get(slot_id, 1)
    n = max(1, n)
    frame_w = max(1, w // n) if n > 1 else w
    meta = {
        "file": hero_rel(slot_id),
        "frames": n,
        "frameWidth": frame_w,
        "frameHeight": h,
        "facing": "right" if n != 4 else "mixed",
        "keyed": keyed,
        "width": w,
        "height": h,
    }
    # 躯干核心高写入 fighter，供对战端 baseScale 使用（忽略翎羽/兵器尖刺）
    try:
        from score import measure_strip_body

        body_h = int(measure_strip_body(im.convert("RGBA"), n).get("body_h") or 0)
        if body_h > 8:
            meta["bodyH"] = body_h
    except Exception:  # noqa: BLE001
        pass
    return meta


def _extract_frame_cell(sheet: Image.Image, frame_index: int, frames: int) -> Image.Image:
    w, h = sheet.size
    fw = max(1, w // max(1, int(frames or 1)))
    x0 = max(0, int(frame_index) * fw)
    return sheet.crop((x0, 0, min(w, x0 + fw), h))


def _scan_front_face_center(cell: Image.Image, ink: tuple[int, int, int, int]) -> tuple[float, float]:
    min_x, min_y, max_x, max_y = ink
    ink_w = max_x - min_x + 1
    ink_h = max_y - min_y + 1
    px = cell.load()
    x0 = min_x + int(ink_w * 0.28)
    x1 = min_x + int(ink_w * 0.72)
    y1 = min_y + int(ink_h * 0.34)
    best_y, best_c = min_y, 0
    for y in range(min_y, y1):
        c = 0
        for x in range(x0, x1, 2):
            r, g, b, a = px[x, y]
            if _is_sheet_bg(r, g, b, a):
                continue
            c += 1
        if c > best_c:
            best_c, best_y = c, y
    if best_c < 8:
        return min_x + ink_w * 0.5, min_y + ink_h * 0.14
    y0 = max(min_y, best_y - 10)
    y2 = min_y + int(ink_h * 0.3)
    sx = sy = n = 0
    for y in range(y0, y2):
        for x in range(x0, x1, 2):
            r, g, b, a = px[x, y]
            if _is_sheet_bg(r, g, b, a):
                continue
            sx += x
            sy += y
            n += 1
    if n < 6:
        return min_x + ink_w * 0.5, min_y + ink_h * 0.14
    return sx / n, sy / n


def _scan_side_face_center(cell: Image.Image, ink: tuple[int, int, int, int]) -> tuple[float, float]:
    min_x, min_y, max_x, max_y = ink
    ink_w = max_x - min_x + 1
    ink_h = max_y - min_y + 1
    px = cell.load()
    x0 = min_x + int(ink_w * 0.12)
    x1 = min_x + int(ink_w * 0.52)
    y1 = min_y + int(ink_h * 0.32)
    best_y, best_c = min_y, 0
    for y in range(min_y, y1):
        c = 0
        for x in range(x0, x1, 2):
            r, g, b, a = px[x, y]
            if _is_sheet_bg(r, g, b, a):
                continue
            c += 1
        if c > best_c:
            best_c, best_y = c, y
    if best_c < 8:
        return min_x + ink_w * 0.28, min_y + ink_h * 0.15
    y0 = max(min_y, best_y - 10)
    y2 = min_y + int(ink_h * 0.28)
    sx = sy = n = 0
    for y in range(y0, y2):
        for x in range(x0, x1, 2):
            r, g, b, a = px[x, y]
            if _is_sheet_bg(r, g, b, a):
                continue
            sx += x
            sy += y
            n += 1
    if n < 6:
        return min_x + ink_w * 0.28, min_y + ink_h * 0.15
    return sx / n, sy / n


def portrait_crop_box(cell: Image.Image, *, is_front: bool) -> tuple[int, int, int]:
    fw, fh = cell.size
    fallback_size = max(8, round(min(fw, fh) * (0.42 if is_front else 0.34)))
    fallback = (
        round((fw - fallback_size) * 0.5),
        round(fh * (0.02 if is_front else 0.05)),
        fallback_size,
    )
    ink = ink_bbox(cell)
    if not ink:
        return fallback
    min_x, min_y, max_x, max_y = ink
    ink_w = max_x - min_x + 1
    ink_h = max_y - min_y + 1
    if is_front:
        fcx, fcy = _scan_front_face_center(cell, ink)
        crop_size = round(max(48, min(ink_h * 0.34, ink_w * 0.62, fw * 0.55)))
        cx_bias, cy_bias = 0.5, 0.4
    else:
        fcx, fcy = _scan_side_face_center(cell, ink)
        crop_size = round(max(48, min(ink_h * 0.3, ink_w * 0.42, fw * 0.55)))
        cx_bias, cy_bias = 0.4, 0.42
    crop_x = round(fcx - crop_size * cx_bias)
    crop_y = round(fcy - crop_size * cy_bias)
    crop_x = max(0, min(crop_x, max(0, fw - crop_size)))
    crop_y = max(0, min(crop_y, max(0, fh - crop_size)))
    crop_size = min(crop_size, fw - crop_x, fh - crop_y)
    return crop_x, crop_y, crop_size


def resolve_select_source(
    hero_id: str,
    *,
    source_slot: str | None = None,
) -> tuple[str, Path, bool] | None:
    """Pick turnaround (front) or idle sheet for roster select bake. Returns (slot, path, is_front)."""
    preferred = (source_slot or "").strip()
    candidates = (preferred,) if preferred in ("turnaround", "idle") else ("turnaround", "idle")
    for slot in candidates:
        path = committed_hero_png(hero_id, slot)
        if path and path.exists():
            return slot, path, slot == "turnaround"
    if preferred:
        # Explicit slot missing — fall back to auto order.
        for slot in ("turnaround", "idle"):
            path = committed_hero_png(hero_id, slot)
            if path and path.exists():
                return slot, path, slot == "turnaround"
    return None


def select_source_cell(
    hero_id: str,
    *,
    source_slot: str | None = None,
) -> tuple[str, Image.Image, tuple[int, int, int]] | None:
    """Load frame-0 cell + auto-suggested square crop (x, y, size) in cell pixels."""
    resolved = resolve_select_source(hero_id, source_slot=source_slot)
    if not resolved:
        return None
    src_slot, src_path, is_front = resolved
    fighter = _read_json(fighter_path(hero_id))
    sprites = fighter.get("sprites") if isinstance(fighter.get("sprites"), dict) else {}
    meta = sprites.get(src_slot) if isinstance(sprites.get(src_slot), dict) else {}
    frames = max(1, int(meta.get("frames") or FRAME_SLOTS.get(src_slot) or 1))
    sheet = Image.open(src_path).convert("RGBA")
    cell = _extract_frame_cell(sheet, 0, frames)
    suggest = portrait_crop_box(cell, is_front=is_front)
    return src_slot, cell, suggest


def _clamp_square_crop(
    cell_w: int,
    cell_h: int,
    crop_x: int,
    crop_y: int,
    crop_size: int,
) -> tuple[int, int, int]:
    max_side = max(8, min(int(cell_w), int(cell_h)))
    size = max(8, min(int(crop_size), max_side))
    x = max(0, min(int(crop_x), max(0, cell_w - size)))
    y = max(0, min(int(crop_y), max(0, cell_h - size)))
    size = min(size, cell_w - x, cell_h - y)
    return x, y, max(8, size)


def bake_hero_select_portrait(
    hero_id: str,
    *,
    size: int = SELECT_PORTRAIT_SIZE,
    source_slot: str | None = None,
    crop: tuple[int, int, int] | None = None,
) -> Path | None:
    """Bake roster-card select.png from turnaround/idle frame 0.

    crop: optional (x, y, size) in source-cell pixels. None → auto face crop.
    """
    loaded = select_source_cell(hero_id, source_slot=source_slot)
    if not loaded:
        return None
    src_slot, cell, suggest = loaded
    if crop is None:
        crop_x, crop_y, crop_size = suggest
    else:
        crop_x, crop_y, crop_size = _clamp_square_crop(cell.size[0], cell.size[1], *crop)
    face = cell.crop((crop_x, crop_y, crop_x + crop_size, crop_y + crop_size))
    out = face.resize((size, size), Image.Resampling.NEAREST)

    dest = game_hero_select_png(hero_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _archive_game_png(dest)
    out.save(dest, format="PNG")

    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    fighter = _read_json(fighter_path(hero_id))
    fighter.setdefault("sprites", {})["select"] = {
        "file": "select.png",
        "width": size,
        "height": size,
        "keyed": True,
        "source": src_slot,
        "crop": {"x": crop_x, "y": crop_y, "size": crop_size, "manual": crop is not None},
        "committedAt": stamp,
    }
    _write_json(fighter_path(hero_id), fighter)
    refresh_index()
    return dest


def bake_all_hero_select_portraits() -> list[dict]:
    results: list[dict] = []
    for path in sorted(paths.game.glob("heroes/*/fighter.json")):
        hero_id = path.parent.name
        try:
            dest = bake_hero_select_portrait(hero_id)
            results.append(
                {
                    "hero_id": hero_id,
                    "ok": bool(dest),
                    "path": str(dest.relative_to(paths.game)) if dest else "",
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append({"hero_id": hero_id, "ok": False, "error": str(exc)})
    return results


def upsert_fighter(
    hero_id: str,
    bible: dict,
    slot_id: str,
    png: Path,
    keyed: bool,
    frames: int | None = None,
) -> dict:
    data = _read_json(fighter_path(hero_id))
    data.update(
        {
            "id": hero_id,
            "displayName": bible.get("display_name") or data.get("displayName") or hero_id,
            "oneLiner": bible.get("one_liner") or data.get("oneLiner") or "",
            "visualLock": bible.get("visual_lock") or data.get("visualLock") or "",
            "homeStageId": bible.get("home_stage_id") or data.get("homeStageId") or "",
            "kit": bible.get("kit") or data.get("kit") or {},
        }
    )
    voice = bible.get("voice")
    if voice:
        existing_lines = (data.get("voice") or {}).get("lines") or {}
        data["voice"] = {
            "persona": voice.get("persona") or "",
            "gender": voice.get("gender") or "male",
            "ttsEngine": voice.get("tts_engine") or "gemini",
            "ttsModel": voice.get("tts_model") or "",
            "ttsVoice": voice.get("tts_voice") or "",
            "ttsLanguage": voice.get("tts_language") or "cmn-CN",
            "voiceAge": voice.get("voice_age") or "adult",
            "speakingRate": voice.get("speaking_rate") or 1,
            "pitch": voice.get("pitch") or 0,
            "lines": {
                line_id: {
                    **(existing_lines.get(line_id) if isinstance(existing_lines.get(line_id), dict) else {}),
                    **(item if isinstance(item, dict) else {"text": item}),
                    "text": (item.get("text") if isinstance(item, dict) else item) or "",
                }
                for line_id, item in (voice.get("lines") or {}).items()
                if (item.get("text") if isinstance(item, dict) else item)
            },
        }
    sync_moves_into_fighter(data, bible)
    sprites = data.setdefault("sprites", {})
    cgs = data.setdefault("cgs", {})
    meta = sprite_meta(png, slot_id, keyed, frames=frames)
    meta["committedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    fx_move = move_id_from_fx_slot(slot_id)
    if fx_move:
        sprites.pop(slot_id, None)
        data["moves"] = attach_fx_meta(data.get("moves") or {}, fx_move, meta, bible.get("kit") if isinstance(bible.get("kit"), dict) else data.get("kit"))
    else:
        if slot_id in CG_FILES:
            cgs.pop(CG_KEYS.get(slot_id, slot_id), None)
        sprites[slot_id] = meta
    _write_json(fighter_path(hero_id), data)
    return data


def upsert_fighter_voice(hero_id: str, bible: dict, clips: dict[str, str]) -> dict:
    data = _read_json(fighter_path(hero_id))
    data.update(
        {
            "id": hero_id,
            "displayName": bible.get("display_name") or data.get("displayName") or hero_id,
            "oneLiner": bible.get("one_liner") or data.get("oneLiner") or "",
            "kit": bible.get("kit") or data.get("kit") or {},
        }
    )
    voice = bible.get("voice") or {}
    lines_out: dict[str, dict] = {}
    for line_id, raw in (voice.get("lines") or {}).items():
        item = raw if isinstance(raw, dict) else {"text": raw}
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        entry: dict = {**item, "text": text}
        if line_id in clips:
            entry["file"] = clips[line_id]
        elif isinstance((data.get("voice") or {}).get("lines", {}).get(line_id), dict):
            prev = data["voice"]["lines"][line_id]
            if prev.get("file"):
                entry["file"] = prev["file"]
        lines_out[line_id] = entry
    data["voice"] = {
        "persona": voice.get("persona") or "",
        "gender": voice.get("gender") or "male",
        "ttsEngine": voice.get("tts_engine") or "gemini",
        "ttsModel": voice.get("tts_model") or "",
        "ttsVoice": voice.get("tts_voice") or "",
        "speakingRate": voice.get("speaking_rate") or 1,
        "pitch": voice.get("pitch") or 0,
        "lines": lines_out,
    }
    _write_json(fighter_path(hero_id), data)
    refresh_index()
    return data


def remove_fighter_slot(hero_id: str, slot_id: str) -> dict:
    data = _read_json(fighter_path(hero_id))
    data.setdefault("sprites", {}).pop(slot_id, None)
    if slot_id in CG_FILES:
        data.setdefault("cgs", {}).pop(CG_KEYS.get(slot_id, slot_id), None)
    fx_move = move_id_from_fx_slot(slot_id)
    if fx_move and isinstance(data.get("moves"), dict) and fx_move in data["moves"]:
        data["moves"][fx_move]["projectile"] = None
    if data:
        _write_json(fighter_path(hero_id), data)
    refresh_index()
    return data


def upsert_stage(stage_id: str, bible: dict, png: Path) -> dict:
    im = Image.open(png)
    w, h = im.size
    existing = _read_json(stage_manifest_path(stage_id))
    collision = sanitize_stage_collision(bible.get("collision") or existing.get("collision"))
    data = {
        "id": stage_id,
        "displayName": bible.get("display_name") or stage_id,
        "visual": bible.get("visual") or "",
        "file": "stage.png",
        "width": w,
        "height": h,
        "collision": collision,
        "committedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if existing.get("bgm"):
        data["bgm"] = existing["bgm"]
    if existing.get("bgmMeta"):
        data["bgmMeta"] = existing["bgmMeta"]
    _write_json(stage_manifest_path(stage_id), data)
    return data


def upsert_stage_bgm(stage_id: str, meta: dict) -> dict:
    manifest = _read_json(stage_manifest_path(stage_id))
    if not manifest:
        raise FileNotFoundError(f"stage.json 不存在：{stage_id}")
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    bgm_meta = dict(meta or {})
    bgm_meta["committedAt"] = stamp
    manifest["bgm"] = "bgm.mp3"
    manifest["bgmMeta"] = bgm_meta
    _write_json(stage_manifest_path(stage_id), manifest)
    return manifest


def remove_stage(stage_id: str) -> None:
    game_dir = paths.game / "stages" / stage_id
    if game_dir.exists() and game_dir.is_dir():
        shutil.rmtree(game_dir)
    refresh_index()


SKIP_HEROES = {"nurhaci_13_armors", "id_1786855456", "id_1786858227"}

DEFAULT_STAGE_COLLISION = {
    "floors": [{"x": 0, "y": 0.84, "w": 1, "h": 0.06}],
    "platforms": [],
    "pits": [],
}


def sanitize_stage_collision(raw: dict | None) -> dict:
    src = raw if isinstance(raw, dict) else {}

    def boxes(items: object, pit: bool) -> list[dict]:
        out = []
        if not isinstance(items, list):
            return out
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                x = min(0.98, max(0.0, float(item.get("x") or 0)))
                y = min(0.98, max(0.0, float(item.get("y") or 0.84)))
                w = min(1.0, max(0.02, float(item.get("w") or 0.1)))
                h = min(0.55, max(0.02, float(item.get("h") or 0.06)))
            except (TypeError, ValueError):
                continue
            box = {"x": x, "y": y, "w": min(w, 1 - x), "h": min(h, 1 - y)}
            if pit:
                box["kill"] = "ko" if item.get("kill") == "ko" else "none"
            out.append(box)
        return out

    floors = boxes(src.get("floors"), False)
    platforms = boxes(src.get("platforms"), False)
    pits_in = boxes(src.get("pits"), True)
    pits: list[dict] = []
    for p in pits_in:
        if p.get("kill") == "ko":
            # 旧地形杀 → 用该框底边附近当站立面；不挪动其它已画矩形
            ditch_y = min(0.965, max(0.2, p["y"] + max(0.04, p["h"] * 0.85)))
            floors.append({"x": p["x"], "y": ditch_y, "w": p["w"], "h": 0.05})
        else:
            pits.append(p)
    if not floors and not platforms:
        return json.loads(json.dumps(DEFAULT_STAGE_COLLISION))
    return {"floors": floors, "platforms": platforms, "pits": pits}


def refresh_index() -> dict:
    heroes = sorted(
        p.parent.name
        for p in paths.game.glob("heroes/*/fighter.json")
        if p.parent.name not in SKIP_HEROES
    )
    stages = sorted(
        p.parent.name
        for p in paths.game.glob("stages/*/stage.json")
    )
    data = {
        "heroes": heroes,
        "stages": stages,
        "style": game_style_png().exists(),
    }
    _write_json(index_path(), data)
    return data


# 人物动作条（不含弹道 fx_*、三视图）：用 idle 躯干对齐各套图体积。
# 一键统一尺寸仍跳过 CG（出场/战败/战胜），避免批量重贴误伤；身长校对工作区单独包含 CG。
_BODY_UNIFY_SKIP = frozenset({"turnaround", *CG_FILES.keys()})
_BODY_SCALE_SKIP = frozenset({"turnaround"})
BODY_UNIFY_SLOTS = tuple(
    sid for sid in FRAME_SLOTS if not str(sid).startswith("fx_") and sid not in _BODY_UNIFY_SKIP
)
BODY_SCALE_SLOTS = tuple(
    sid for sid in FRAME_SLOTS if not str(sid).startswith("fx_") and sid not in _BODY_SCALE_SKIP
)


def _archive_game_png(path: Path) -> None:
    if not path.exists():
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bak = path.parent / "_bak"
    bak.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, bak / f"{path.stem}_unify_{stamp}{path.suffix}")


def _save_game_sheet(sheet: Image.Image, path: Path, *, frames: int) -> Image.Image:
    """Write a hero strip to disk after chroma-keying cyan → transparent (game has no runtime key).

    Skip comic-gutter scrub: body-scale/unify packs already-clean cells onto cyan;
    scrub can carve dark clothing belts and break head/feet measurement.
    """
    keyed = cyan_key_image(sheet, frames=max(1, int(frames or 1)), strict=False, scrub=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    keyed.save(path, format="PNG")
    return keyed


def unify_hero_body_scale(hero_id: str, *, ref_slot: str = "idle") -> dict:
    """
    不重新生图：以 ref_slot（默认 idle）人物墨迹高度为基准，
    把已入库的各动作条按 NEAREST 缩放对齐，并更新 fighter.json 的 sprites 尺寸。
    """
    ensure_dirs()
    fighter = _read_json(fighter_path(hero_id))
    sprites = fighter.get("sprites") if isinstance(fighter.get("sprites"), dict) else {}
    ref_path = committed_hero_png(hero_id, ref_slot)
    if not ref_path or not ref_path.exists():
        raise FileNotFoundError(f"缺少基准套图「{ref_slot}」，请先入库原地呼吸。")
    ref_meta = sprites.get(ref_slot) if isinstance(sprites.get(ref_slot), dict) else {}
    ref_frames = int(ref_meta.get("frames") or FRAME_SLOTS.get(ref_slot) or 5)
    ref_im = Image.open(ref_path).convert("RGBA")
    ref_m = measure_strip_body(ref_im, ref_frames)
    if not ref_m.get("body_h"):
        raise ValueError(f"基准套图「{ref_slot}」测不到人物墨迹。")
    target_h = int(ref_m["body_h"])
    target_feet = int(ref_m["feet_y"])
    target_fh = int(ref_m["frame_h"])

    reports: list[dict] = []
    changed = 0
    for slot_id in BODY_UNIFY_SLOTS:
        path = committed_hero_png(hero_id, slot_id)
        if not path or not path.exists():
            continue
        meta = sprites.get(slot_id) if isinstance(sprites.get(slot_id), dict) else {}
        n = int(meta.get("frames") or FRAME_SLOTS.get(slot_id) or 5)
        if slot_id == ref_slot:
            reports.append(
                {
                    "slot": slot_id,
                    "skipped": True,
                    "reason": "reference",
                    "before": target_h,
                    "after": target_h,
                    "scale": 1.0,
                }
            )
            continue
        im = Image.open(path).convert("RGBA")
        sheet, info = rescale_strip_to_body(
            im,
            n,
            target_h,
            target_feet,
            target_frame_h=target_fh,
            preserve_air_lift=slot_id in AIR_SLOTS,
        )
        info = {**info, "slot": slot_id}
        reports.append(info)
        if info.get("skipped"):
            continue
        _archive_game_png(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        sheet = _save_game_sheet(sheet, path, frames=n)
        src = source_hero_png(hero_id, slot_id)
        if src.exists():
            _archive_game_png(src)
            sheet.save(src, format="PNG")
        clear_split_frames(hero_id, slot_id)
        bible = {
            "display_name": fighter.get("displayName"),
            "one_liner": fighter.get("oneLiner"),
            "visual_lock": fighter.get("visualLock"),
            "home_stage_id": fighter.get("homeStageId"),
            "kit": fighter.get("kit") or {},
            "voice": fighter.get("voice"),
            "moves": fighter.get("moves"),
        }
        # 重新读 fighter，避免循环里覆盖彼此
        fighter = upsert_fighter(hero_id, bible, slot_id, path, keyed=True, frames=n)
        sprites = fighter.get("sprites") if isinstance(fighter.get("sprites"), dict) else {}
        changed += 1

    return {
        "hero_id": hero_id,
        "ref_slot": ref_slot,
        "ref_body_h": target_h,
        "ref_feet_y": target_feet,
        "changed": changed,
        "slots": reports,
    }


def _hero_slot_frame_count(hero_id: str, slot_id: str) -> int:
    """Prefer committed strip geometry / fighter meta / cells.json over FRAME_SLOTS.

    Body-scale can shorten a strip (6→4). Later equal-width cuts must use the new N,
    not the generation default.
    """
    fighter = _read_json(fighter_path(hero_id))
    sprites = fighter.get("sprites") if isinstance(fighter.get("sprites"), dict) else {}
    meta = sprites.get(slot_id) if isinstance(sprites.get(slot_id), dict) else {}
    n_meta = 0
    try:
        n_meta = int(meta.get("frames") or 0)
    except (TypeError, ValueError):
        n_meta = 0
    fw = 0
    try:
        fw = int(meta.get("frameWidth") or 0)
    except (TypeError, ValueError):
        fw = 0
    path = committed_hero_png(hero_id, slot_id)
    implied = _strip_implied_frames(path, fw) if fw > 0 else None
    if implied and implied >= 1:
        # Strip width ÷ frameWidth wins when fighter.frames is stale after a short save.
        return implied
    if n_meta >= 1:
        return n_meta
    n_cells = _cells_frame_count(hero_id, slot_id)
    if n_cells:
        return n_cells
    files = list_split_frames(hero_id, slot_id)
    if files:
        return len(files)
    return int(FRAME_SLOTS.get(slot_id) or 5)


# 全库默认头↔脚参考躯干高（身长校对青/绿准线）。可按倍率覆盖：
# 0.5×～1.5× → 280～840px；visualScale = guide / 560，游戏用同一夹取，无高矮特例。
DEFAULT_BODY_GUIDE_H = 560
VISUAL_SCALE_MIN = 0.5
VISUAL_SCALE_MAX = 1.5
MIN_BODY_GUIDE_H = int(round(DEFAULT_BODY_GUIDE_H * VISUAL_SCALE_MIN))  # 280
MAX_BODY_GUIDE_H = int(round(DEFAULT_BODY_GUIDE_H * VISUAL_SCALE_MAX))  # 840


def _clamp_visual_scale(vs: float) -> float:
    return round(max(VISUAL_SCALE_MIN, min(VISUAL_SCALE_MAX, float(vs))), 4)


def resolve_body_guide_h(hero_id: str) -> dict:
    """Library-standard guide span, with optional per-hero override for giant/short builds."""
    fighter = _read_json(fighter_path(hero_id))
    raw = fighter.get("bodyGuideH", fighter.get("body_guide_h"))
    custom = None
    if raw is not None and str(raw).strip() != "":
        try:
            custom = int(round(float(raw)))
        except (TypeError, ValueError):
            custom = None
    if custom is not None:
        guide = max(MIN_BODY_GUIDE_H, min(MAX_BODY_GUIDE_H, custom))
        mode = "custom"
    else:
        guide = DEFAULT_BODY_GUIDE_H
        mode = "default"
    vs = None
    try:
        vs = float(fighter.get("visualScale"))
    except (TypeError, ValueError):
        vs = None
    if not vs or vs <= 0:
        vs = guide / float(DEFAULT_BODY_GUIDE_H)
    return {
        "guide_body_h": int(guide),
        "default_body_guide_h": int(DEFAULT_BODY_GUIDE_H),
        "guide_mode": mode,
        "visual_scale": _clamp_visual_scale(vs),
        "visual_scale_min": VISUAL_SCALE_MIN,
        "visual_scale_max": VISUAL_SCALE_MAX,
    }


def set_hero_body_guide(hero_id: str, body_guide_h: int | None, *, sync_visual_scale: bool = True) -> dict:
    """Set/clear per-hero workshop guide span. None → library default.

    When sync_visual_scale, game visualScale = guide/DEFAULT（夹在 0.5～1.5），高矮同一公式。
    """
    ensure_dirs()
    path = fighter_path(hero_id)
    data = _read_json(path)
    if body_guide_h is None:
        data.pop("bodyGuideH", None)
        data.pop("body_guide_h", None)
        guide = DEFAULT_BODY_GUIDE_H
        mode = "default"
    else:
        guide = max(MIN_BODY_GUIDE_H, min(MAX_BODY_GUIDE_H, int(round(body_guide_h))))
        data["bodyGuideH"] = guide
        data.pop("body_guide_h", None)
        mode = "custom"
    if sync_visual_scale:
        data["visualScale"] = _clamp_visual_scale(guide / float(DEFAULT_BODY_GUIDE_H))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "hero_id": hero_id,
        "guide_body_h": int(guide),
        "default_body_guide_h": int(DEFAULT_BODY_GUIDE_H),
        "guide_mode": mode,
        "visual_scale": data.get("visualScale"),
        "visual_scale_min": VISUAL_SCALE_MIN,
        "visual_scale_max": VISUAL_SCALE_MAX,
    }


def measure_hero_ref_body(hero_id: str, ref_slot: str = "idle") -> dict:
    path = committed_hero_png(hero_id, ref_slot)
    if not path or not path.exists():
        raise FileNotFoundError(f"缺少基准套图「{ref_slot}」，请先入库。")
    n = _hero_slot_frame_count(hero_id, ref_slot)
    m = measure_strip_body(Image.open(path).convert("RGBA"), n)
    if not m.get("body_h"):
        raise ValueError(f"基准套图「{ref_slot}」测不到躯干身高。")
    guide = resolve_body_guide_h(hero_id)
    idle_h = int(m["body_h"])
    # Guides / unify target the library (or custom) span; feet stay on measured idle.
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


def ensure_committed_equal_frames(hero_id: str, slot_id: str, *, force: bool = False) -> list[Path]:
    """
    Ensure draft split frames exist for body-scale review.
    Prefer equal-width slices of the *committed* game strip (not generative re-pack).
    """
    dest = draft_hero_frames_dir(hero_id, slot_id)
    path = committed_hero_png(hero_id, slot_id)
    if not path or not path.exists():
        raise FileNotFoundError(f"套图「{slot_id}」尚未入库。")
    n = _hero_slot_frame_count(hero_id, slot_id)
    existing = list_split_frames(hero_id, slot_id)
    if existing and len(existing) == n and not force:
        try:
            newest_frame = max(p.stat().st_mtime for p in existing)
            if newest_frame >= path.stat().st_mtime - 0.05:
                return existing
        except OSError:
            pass

    im = Image.open(path).convert("RGBA")
    w, h = im.size
    fw = max(1, w // max(1, n))
    clear_split_frames(hero_id, slot_id)
    dest.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for i in range(n):
        cell = im.crop((i * fw, 0, min(w, (i + 1) * fw), h))
        fp = dest / f"{i:02d}.png"
        cell.save(fp, format="PNG")
        out.append(fp)
    meta = {
        "variant": -1,
        "label": "入库条等宽切分（身长校对）",
        "expected": n,
        "split_frames": n,
        "applied": True,
        "cells": [],
        "source": "body_scale_workspace",
    }
    (dest / "cells.json").write_text(json.dumps(meta), encoding="utf-8")
    return out


def list_body_scale_workspace(
    hero_id: str,
    *,
    ref_slot: str = "idle",
    titles: dict[str, str] | None = None,
    tol: float = 0.04,
) -> dict:
    ref = measure_hero_ref_body(hero_id, ref_slot)
    target = int(ref["ref_body_h"])
    title_map = dict(titles or {})
    slots: list[dict] = []
    for slot_id in BODY_SCALE_SLOTS:
        path = committed_hero_png(hero_id, slot_id)
        if not path or not path.exists():
            continue
        n = _hero_slot_frame_count(hero_id, slot_id)
        m = measure_strip_body(Image.open(path).convert("RGBA"), n)
        body_h = int(m.get("body_h") or 0)
        delta = body_h - target
        ok = body_h > 0 and abs(delta) / max(1, target) <= tol
        slots.append(
            {
                "id": slot_id,
                "title": title_map.get(slot_id) or slot_id,
                "frames": n,
                "body_h": body_h,
                "dense_h": int(m.get("dense_h") or 0),
                "delta": delta,
                "ok": ok,
                "is_ref": slot_id == ref_slot,
            }
        )
    return {
        "hero_id": hero_id,
        **ref,
        "tol": tol,
        "slots": slots,
        "ok_count": sum(1 for s in slots if s["ok"]),
        "warn_count": sum(1 for s in slots if not s["ok"]),
    }


def place_cell_on_canvas(
    cell: Image.Image,
    *,
    scale: float = 1.0,
    target_feet_y: int,
    target_frame_h: int,
    min_frame_w: int = 64,
    feet_dy: int = 0,
    y_shift: int = 0,
    mirror: bool = False,
) -> Image.Image:
    """NEAREST-scale cell ink and pin core feet to target_feet_y on a cyan canvas.

    feet_dy: positive lifts the figure (feet drawn higher / smaller Y); negative lowers it.
    y_shift: shared downward shift for a whole strip so tall poses never get a
    per-frame emergency shift that destroys relative air lifts.
    mirror: horizontal flip before place.
    Canvas grows as needed so boots / trailing pixels below the core-feet line
    are never cropped.
    """
    scale = max(0.35, min(3.0, float(scale or 1.0)))
    src = cell.convert("RGBA")
    if mirror:
        src = src.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    core = measure_cell_body(src)
    bb = ink_bbox(src)
    y_shift = max(0, int(y_shift or 0))
    fh = max(24, int(target_frame_h) + y_shift)
    # Positive feet_dy → pin feet higher on the canvas (above the default ground line).
    feet_y = int(target_feet_y) - int(feet_dy or 0) + y_shift
    if not bb or not core.get("body_h"):
        fw = max(min_frame_w, src.size[0])
        canvas = Image.new("RGBA", (fw, fh), CYAN_FILL)
        canvas.paste(src, ((fw - src.size[0]) // 2, max(0, (fh - src.size[1]) // 2)), src)
        return canvas

    x0, y0, x1, y1 = bb
    pad = 6
    crop_y0 = max(0, y0 - pad)
    crop = src.crop(
        (
            max(0, x0 - pad),
            crop_y0,
            min(src.size[0], x1 + 1 + pad),
            min(src.size[1], y1 + 1 + pad),
        )
    )
    nw = max(1, int(round(crop.size[0] * scale)))
    nh = max(1, int(round(crop.size[1] * scale)))
    scaled = crop.resize((nw, nh), Image.Resampling.NEAREST)
    core_feet = int(core["feet_y"])
    feet_in_crop = (core_feet - crop_y0) + 1
    feet_scaled = max(1, int(round(feet_in_crop * scale)))
    below_feet = max(0, nh - feet_scaled)
    top = feet_y - feet_scaled + 1
    fw = max(min_frame_w, nw + 16, src.size[0])

    # With a proper strip-wide y_shift, top should be >= 0. Keep a safety net
    # but do not silently rewrite feet_y (that used to flatten jump apexes).
    if top < 0:
        scaled_pad = Image.new("RGBA", (nw, nh - top), CYAN_FILL)
        scaled_pad.paste(scaled, (0, -top), scaled)
        scaled = scaled_pad
        nh = scaled.size[1]
        feet_scaled += -top
        top = 0
    fh = max(fh, top + nh + 8, feet_y + below_feet + 10)
    canvas = Image.new("RGBA", (fw, fh), CYAN_FILL)
    left = (fw - nw) // 2
    canvas.paste(scaled, (left, top), scaled)
    return canvas


def _plan_place_top(
    cell: Image.Image,
    *,
    scale: float,
    target_feet_y: int,
    feet_dy: int,
) -> int:
    """Preview the `top` Y that place_cell_on_canvas would use (before y_shift)."""
    scale = max(0.35, min(3.0, float(scale or 1.0)))
    src = cell.convert("RGBA")
    core = measure_cell_body(src)
    bb = ink_bbox(src)
    feet_y = int(target_feet_y) - int(feet_dy or 0)
    if not bb or not core.get("body_h"):
        return 0
    x0, y0, x1, y1 = bb
    pad = 6
    crop_y0 = max(0, y0 - pad)
    feet_in_crop = (int(core["feet_y"]) - crop_y0) + 1
    feet_scaled = max(1, int(round(feet_in_crop * scale)))
    return feet_y - feet_scaled + 1


def describe_body_scale_slot(
    hero_id: str,
    slot_id: str,
    *,
    ref_slot: str = "idle",
    titles: dict[str, str] | None = None,
    tol: float = 0.04,
    ensure: bool = True,
) -> dict:
    ref = measure_hero_ref_body(hero_id, ref_slot)
    target = int(ref["ref_body_h"])
    if ensure:
        ensure_committed_equal_frames(hero_id, slot_id)
    files = list_split_frames(hero_id, slot_id)
    if len(files) < 1:
        raise FileNotFoundError(f"套图「{slot_id}」没有可校对的帧。")
    title_map = dict(titles or {})
    frames_out: list[dict] = []
    raw_feet: list[int | None] = []
    for i, fp in enumerate(files):
        cell = Image.open(fp).convert("RGBA")
        m = measure_cell_body(cell)
        body_h = int(m.get("body_h") or 0)
        delta = body_h - target
        ok = body_h > 0 and abs(delta) / max(1, target) <= tol
        feet_y = int(m.get("feet_y") or 0) if body_h > 0 else None
        raw_feet.append(feet_y)
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
                "width": cell.size[0],
                "height": cell.size[1],
            }
        )
    air_acting = slot_id in AIR_SLOTS
    if air_acting:
        cells = [Image.open(fp).convert("RGBA") for fp in files]
        lifts = air_lifts_from_cells(cells)
    else:
        lifts = [0] * len(frames_out)
    for i, fr in enumerate(frames_out):
        fr["ground_lift"] = int(lifts[i]) if i < len(lifts) else 0
    body_hs = [f["body_h"] for f in frames_out if f["body_h"] > 0]
    slot_body = int(median(body_hs)) if body_hs else 0
    slot_delta = slot_body - target
    return {
        "hero_id": hero_id,
        "slot_id": slot_id,
        "title": title_map.get(slot_id) or slot_id,
        "is_ref": slot_id == ref_slot,
        "air_acting": air_acting,
        **ref,
        "tol": tol,
        "body_h": slot_body,
        "delta": slot_delta,
        "ok": slot_body > 0 and abs(slot_delta) / max(1, target) <= tol,
        "frames": frames_out,
    }


def save_body_scale_slot(
    hero_id: str,
    slot_id: str,
    scales: dict[int, float] | None = None,
    *,
    ref_slot: str = "idle",
    feet_dys: dict[int, int] | None = None,
    mirrors: dict[int, bool] | None = None,
    order: list[int] | None = None,
) -> dict:
    """
    Apply per-frame NEAREST scales + optional feet_dy (positive = lift),
    optional horizontal mirror, rebuild playback from `order`,
    drop unused source frames, pin feet / preserve air lift, write strip.
    """
    ensure_dirs()
    ref = measure_hero_ref_body(hero_id, ref_slot)
    ensure_committed_equal_frames(hero_id, slot_id)
    files = list_split_frames(hero_id, slot_id)
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
                raise ValueError(f"帧索引越界：{src_i}（源帧 0..{n_src - 1}）")
    scale_map = {int(k): float(v) for k, v in (scales or {}).items()}
    dy_map = {int(k): int(v) for k, v in (feet_dys or {}).items()}
    mirror_map = {int(k): bool(v) for k, v in (mirrors or {}).items()}
    target_feet = int(ref["ref_feet_y"])
    target_fh = int(ref["ref_frame_h"])
    min_fw = max(64, int(ref.get("ref_frame_w") or 64))

    # Load playback sequence (reuse = read same source file again).
    src_cells = [Image.open(files[src_i]).convert("RGBA") for src_i in perm]
    n = len(src_cells)

    air_acting = slot_id in AIR_SLOTS
    auto_lifts = air_lifts_from_cells(src_cells) if air_acting else [0] * n

    planned: list[dict] = []
    for new_i, cell in enumerate(src_cells):
        scale = scale_map.get(new_i, 1.0)
        user_dy = int(dy_map.get(new_i, 0))
        auto_dy = int(round(auto_lifts[new_i] * float(scale))) if air_acting else 0
        feet_dy = auto_dy + user_dy
        mirror = bool(mirror_map.get(new_i, False))
        plan_cell = cell.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if mirror else cell
        planned.append(
            {
                "cell": cell,
                "scale": scale,
                "feet_dy": feet_dy,
                "auto_dy": auto_dy,
                "user_dy": user_dy,
                "mirror": mirror,
                "top": _plan_place_top(
                    plan_cell, scale=scale, target_feet_y=target_feet, feet_dy=feet_dy
                ),
            }
        )
    # Shared downward shift so tall apex / lifted frames keep relative air height.
    y_shift = max(0, max((-int(p["top"]) for p in planned), default=0))

    rebuilt: list[Image.Image] = []
    applied: list[dict] = []
    for new_i, plan in enumerate(planned):
        cell = plan["cell"]
        scale = plan["scale"]
        feet_dy = plan["feet_dy"]
        mirror = plan["mirror"]
        before = measure_cell_body(cell)
        placed = place_cell_on_canvas(
            cell,
            scale=scale,
            target_feet_y=target_feet,
            target_frame_h=target_fh,
            min_frame_w=min_fw,
            feet_dy=feet_dy,
            y_shift=y_shift,
            mirror=mirror,
        )
        after = measure_cell_body(placed)
        rebuilt.append(placed)
        applied.append(
            {
                "index": new_i,
                "source_index": int(perm[new_i]),
                "scale": round(float(scale), 4),
                "feet_dy": feet_dy,
                "auto_lift": plan["auto_dy"],
                "user_feet_dy": plan["user_dy"],
                "mirror": mirror,
                "y_shift": y_shift,
                "before": int(before.get("body_h") or 0),
                "after": int(after.get("body_h") or 0),
            }
        )

    dest_dir = draft_hero_frames_dir(hero_id, slot_id)
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
        final = dest_dir / f"{i:02d}.png"
        tmp.replace(final)

    fw = max(im.size[0] for im in rebuilt)
    fh = max(im.size[1] for im in rebuilt)
    sheet = Image.new("RGBA", (fw * len(rebuilt), fh), CYAN_FILL)
    for i, im in enumerate(rebuilt):
        cell_canvas = Image.new("RGBA", (fw, fh), CYAN_FILL)
        cell_canvas.paste(im, ((fw - im.size[0]) // 2, 0), im)
        sheet.paste(cell_canvas, (i * fw, 0))

    dest = game_hero_png(hero_id, slot_id)
    _archive_game_png(dest)
    sheet = _save_game_sheet(sheet, dest, frames=len(rebuilt))
    src = source_hero_png(hero_id, slot_id)
    src.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        _archive_game_png(src)
    sheet.save(src, format="PNG")
    draft = draft_hero_png(hero_id, slot_id)
    if draft.exists():
        _archive_game_png(draft)
        sheet.save(draft, format="PNG")

    fighter = _read_json(fighter_path(hero_id))
    bible = {
        "display_name": fighter.get("displayName"),
        "one_liner": fighter.get("oneLiner"),
        "visual_lock": fighter.get("visualLock"),
        "home_stage_id": fighter.get("homeStageId"),
        "kit": fighter.get("kit") or {},
        "voice": fighter.get("voice"),
        "moves": fighter.get("moves"),
    }
    upsert_fighter(hero_id, bible, slot_id, dest, keyed=True, frames=len(rebuilt))
    mark_split_applied(hero_id, slot_id)
    # Persist new frame count into cells.json so later splits/views stay consistent.
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
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    after_strip = measure_strip_body(sheet, len(rebuilt))
    dropped = sorted(set(range(n_src)) - set(perm))
    return {
        "hero_id": hero_id,
        "slot_id": slot_id,
        "ref_slot": ref_slot,
        "ref_body_h": int(ref["ref_body_h"]),
        "order": perm,
        "dropped_sources": dropped,
        "frames_applied": applied,
        "body_h": int(after_strip.get("body_h") or 0),
        "delta": int(after_strip.get("body_h") or 0) - int(ref["ref_body_h"]),
        "frame_count": len(rebuilt),
    }


def body_scale_chart_path(hero_id: str) -> Path:
    return paths.drafts / "heroes" / hero_id / "body_scale_chart.png"


def _chart_font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_body_scale_chart(
    hero_id: str,
    *,
    ref_slot: str = "idle",
    titles: dict[str, str] | None = None,
    tol: float = 0.04,
    max_strip_w: int = 1200,
) -> dict:
    """
    生成身长对照预览图：自上而下叠放各已入库动作条，左侧刻度尺 + 头/脚准线。
    条带会缩到 max_strip_w 以内，避免超大 PNG 卡死浏览器；标注仍用原图像素身长。
    写入 drafts/heroes/<id>/body_scale_chart.png。
    """
    ensure_dirs()
    fighter = _read_json(fighter_path(hero_id))
    sprites = fighter.get("sprites") if isinstance(fighter.get("sprites"), dict) else {}
    title_map = dict(titles or {})
    max_strip_w = max(480, int(max_strip_w or 1200))

    rows_src: list[dict] = []
    for slot_id in BODY_SCALE_SLOTS:
        path = committed_hero_png(hero_id, slot_id)
        if not path or not path.exists():
            continue
        meta = sprites.get(slot_id) if isinstance(sprites.get(slot_id), dict) else {}
        n = int(meta.get("frames") or FRAME_SLOTS.get(slot_id) or 5)
        im = Image.open(path).convert("RGBA")
        m = measure_strip_body(im, n)
        rows_src.append(
            {
                "slot": slot_id,
                "title": title_map.get(slot_id) or slot_id,
                "im": im,
                "m": m,
                "frames": n,
                "is_ref": slot_id == ref_slot,
            }
        )
    if not rows_src:
        raise FileNotFoundError("没有已入库的人物套图，无法生成身长对照图。")

    ref_row = next((r for r in rows_src if r["is_ref"]), None)
    if ref_row is None:
        raise FileNotFoundError(f"缺少基准套图「{ref_slot}」，请先入库。")
    ref_body_h = int(ref_row["m"].get("body_h") or 0)
    if ref_body_h <= 0:
        raise ValueError(f"基准套图「{ref_slot}」测不到人物墨迹。")

    # Downscale for UI; keep original metrics in labels / tick numbers.
    # Only show up to 2 frames per strip — enough to judge body height, avoids huge previews.
    prepared: list[dict] = []
    for r in rows_src:
        im = r["im"]
        m = r["m"]
        n = max(1, int(r["frames"]))
        fw = max(1, im.width // n)
        show_n = min(2, n)
        crop = im.crop((0, 0, min(im.width, fw * show_n), im.height))
        scale = min(1.0, max_strip_w / max(1, crop.width))
        # Also cap row height so 20 strips don't make a 7k-tall page
        max_h = 200
        if crop.height * scale > max_h:
            scale = min(scale, max_h / max(1, crop.height))
        if scale < 0.999:
            nw = max(1, int(round(crop.width * scale)))
            nh = max(1, int(round(crop.height * scale)))
            disp = crop.resize((nw, nh), Image.Resampling.NEAREST)
        else:
            disp = crop
            scale = 1.0
        prepared.append({**r, "disp": disp, "scale": scale})

    ruler_w = 64
    label_w = 188
    pad_top = 48
    pad_bot = 20
    row_gap = 14
    label_h = 34
    max_disp_w = max(int(r["disp"].width) for r in prepared)
    content_w = label_w + max_disp_w + 12
    total_h = pad_top + sum(label_h + int(r["disp"].height) for r in prepared) + row_gap * max(0, len(prepared) - 1) + pad_bot
    chart = Image.new("RGB", (ruler_w + content_w, total_h), (22, 24, 28))
    draw = ImageDraw.Draw(chart)
    font_title = _chart_font(18)
    font_row = _chart_font(15)
    font_small = _chart_font(12)
    font_tick = _chart_font(11)

    who = str(fighter.get("displayName") or hero_id)
    draw.text(
        (ruler_w + 10, 12),
        f"{who} · 身长对照(躯干)  |  基准 {ref_slot} = {ref_body_h}px  |  绿=脚  青=基准头  橙=实测头  |  已忽略武器/粒子尖刺",
        fill=(220, 224, 230),
        font=font_title,
    )

    rows_out: list[dict] = []
    y = pad_top
    ok_count = 0
    warn_count = 0
    for r in prepared:
        disp = r["disp"]
        scale = float(r["scale"])
        m = r["m"]
        body_h = int(m.get("body_h") or 0)
        feet_y = int(m.get("feet_y") or (r["im"].height - 8))
        delta = body_h - ref_body_h
        ratio = abs(delta) / max(1, ref_body_h)
        ok = body_h > 0 and ratio <= tol
        if ok:
            ok_count += 1
        else:
            warn_count += 1
        status = "齐" if ok else ("缺墨" if body_h <= 0 else f"差{delta:+d}")
        status_color = (90, 200, 120) if ok else ((180, 180, 180) if body_h <= 0 else (230, 150, 70))

        row_bottom = y + label_h + disp.height - 1
        draw.rectangle((ruler_w, y, ruler_w + label_w - 8, row_bottom), fill=(30, 33, 38))
        tag = "〔基准〕" if r["is_ref"] else ""
        draw.text((ruler_w + 8, y + 4), f"{r['title']}{tag}", fill=(235, 238, 245), font=font_row)
        draw.text(
            (ruler_w + 8, y + 22),
            f"{r['slot']}  躯干{body_h}px  Δ{delta:+d}  {status}",
            fill=status_color,
            font=font_small,
        )

        strip_x = ruler_w + label_w
        strip_y = y + label_h
        # Flat underlay (no per-tile checker — that froze the UI on huge strips)
        draw.rectangle(
            (strip_x, strip_y, strip_x + disp.width - 1, strip_y + disp.height - 1),
            fill=(40, 44, 50),
        )
        chart.paste(disp, (strip_x, strip_y), disp)

        feet_abs = strip_y + int(round(feet_y * scale))
        head_abs = feet_abs - int(round(ref_body_h * scale))
        measured_head = feet_abs - int(round(body_h * scale)) if body_h else head_abs
        draw.line((strip_x, feet_abs, strip_x + disp.width, feet_abs), fill=(90, 200, 120), width=2)
        draw.line((strip_x, head_abs, strip_x + disp.width, head_abs), fill=(80, 200, 220), width=2)
        if body_h and abs(measured_head - head_abs) > 1:
            draw.line((strip_x, measured_head, strip_x + disp.width, measured_head), fill=(230, 150, 70), width=1)

        rx0, rx1 = 6, ruler_w - 6
        draw.line((rx1, strip_y, rx1, strip_y + disp.height), fill=(90, 96, 108), width=1)
        tick_max = max(ref_body_h, body_h) + 50
        for tick in range(0, tick_max, 50):
            ty = feet_abs - int(round(tick * scale))
            if ty < strip_y - 2 or ty > strip_y + disp.height + 2:
                continue
            major = tick % 100 == 0
            tw = 12 if major else 7
            draw.line((rx1 - tw, ty, rx1, ty), fill=(160, 168, 180) if major else (110, 118, 130), width=1)
            if major or tick == ref_body_h:
                label = f"{tick}" if tick != ref_body_h else f"{tick}★"
                draw.text(
                    (rx0, ty - 6),
                    label,
                    fill=(200, 210, 120) if tick == ref_body_h else (170, 176, 186),
                    font=font_tick,
                )
        ref_mark = feet_abs - int(round(ref_body_h * scale))
        if strip_y <= ref_mark <= strip_y + disp.height:
            draw.line((rx1 - 16, ref_mark, rx1, ref_mark), fill=(80, 200, 220), width=2)

        rows_out.append(
            {
                "slot": r["slot"],
                "title": r["title"],
                "body_h": body_h,
                "feet_y": feet_y,
                "frame_h": int(m.get("frame_h") or r["im"].height),
                "frames": r["frames"],
                "delta": delta,
                "ok": ok,
                "is_ref": r["is_ref"],
            }
        )
        y += label_h + disp.height + row_gap

    out = body_scale_chart_path(hero_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    chart.save(out, format="PNG", compress_level=3)
    return {
        "hero_id": hero_id,
        "ref_slot": ref_slot,
        "ref_body_h": ref_body_h,
        "path": str(out),
        "ok_count": ok_count,
        "warn_count": warn_count,
        "tol": tol,
        "rows": rows_out,
        "width": chart.width,
        "height": chart.height,
        "preview_scale_note": f"strips capped at {max_strip_w}px wide",
    }
