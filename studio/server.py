#!/usr/bin/env python3
"""Local art studio for 英灵大乱斗 sprite generation."""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field

from combat import normalize_moves, sync_moves_into_fighter
from prompts import (
    HERO_SLOTS,
    INFER_SYSTEM,
    PORTRAIT_INFER_SYSTEM,
    PORTRAIT_SLOT_INFER_SYSTEM,
    PORTRAIT_SLOTS,
    PORTRAIT_SLOT_IDS,
    PORTRAIT_DEFAULT_PLAN_IDS,
    PORTRAIT_CHROMA_SAFE,
    PORTRAIT_REF_LABEL_TURNAROUND,
    PORTRAIT_REF_LABEL_STYLE,
    normalize_portrait_slot,
    normalize_portrait_slot_list,
    portrait_infer_system_for,
    SLOT_BY_ID,
    SLOT_INFER_SYSTEM,
    STAGE_INFER_SYSTEM,
    STAGE_SLOT,
    STAGE_TERRAIN_HINTS,
    STYLE_INFER_SYSTEM,
    style_infer_system,
    normalize_product_line,
    STYLE_SLOT,
    VOICE_INFER_SYSTEM,
    VOICE_LINES,
    normalize_voice,
    parse_line,
    with_stage_terrain_prompt,
    wrap_prompt,
    slot_zh_fallback,
    fx_subject_for,
    fx_default_body,
    FX_SUBJECT_MODES,
    STRIP_RETRY,
    FX_STRIP_RETRY,
    FX_FIGURE_STRIP_RETRY,
    FX_CLONE_STRIP_RETRY,
    STRIP_SEPARATION,
    FX_STRIP_SEPARATION,
    FX_FIGURE_STRIP_SEPARATION,
    FX_CLONE_STRIP_SEPARATION,
    TURNAROUND_RETRY,
    REF_LABEL_TURNAROUND,
    REF_LABEL_STYLE,
    REF_LABEL_PHOTO,
)
from score import FRAME_SLOTS, SPLIT_VARIANT_COUNT, SPLIT_VARIANT_LABELS, cyan_key_png, detect_strip_cells, diversity_score, heuristic_score, looks_like_grid_2x2, scrub_panel_borders
from game_assets import (
    clear_split_frames,
    committed_hero_png,
    committed_stage_png,
    committed_stage_bgm,
    committed_style_png,
    committed_voice_mp3,
    draft_hero_frames_dir,
    draft_hero_png,
    draft_clone_audio,
    draft_stage_bgm,
    draft_stage_png,
    draft_style_png,
    draft_voice_mp3,
    ensure_dirs,
    ensure_split_source,
    assemble_split_sheet,
    mark_split_applied,
    next_split_variant,
    remember_split_source,
    source_hero_png,
    fighter_path,
    game_hero_png,
    game_hero_select_png,
    game_stage_png,
    game_stage_bgm,
    game_style_png,
    game_voice_mp3,
    load_split_layout,
    list_split_frames,
    prepare_sprite_sheet,
    refresh_index,
    remove_fighter_slot,
    remove_stage,
    sanitize_stage_collision,
    split_strip,
    upsert_fighter,
    upsert_fighter_voice,
    upsert_stage,
    upsert_stage_bgm,
    stage_manifest_path,
    set_hero_body_guide,
    unify_hero_body_scale,
    build_body_scale_chart,
    list_body_scale_workspace,
    describe_body_scale_slot,
    save_body_scale_slot,
    ensure_committed_equal_frames,
    _hero_slot_frame_count,
    work_hero_png,
    bake_hero_select_portrait,
    bake_all_hero_select_portraits,
    select_source_cell,
)
from packutil import build_pack_zip
from portrait_assets import (
    delete_portrait,
    discard_portrait_slot,
    draft_portrait_png,
    ensure_portrait_dirs,
    export_portrait_dir,
    export_portrait_slot,
    describe_portrait_body_scale_slot,
    list_portrait_body_scale_workspace,
    list_portrait_ids,
    portrait_asset_view,
    portrait_slot_frame_count,
    read_portrait_bible,
    reset_portrait_slot_derivatives,
    resolve_portrait_slots,
    save_portrait_body_scale_slot,
    set_portrait_body_guide,
    split_portrait_strip,
    unify_portrait_body_scale,
    write_portrait_bible,
)
from project import (
    KIND_DESKPET,
    KIND_HEROGAME,
    LINE_LABELS,
    VALID_KINDS,
    boot,
    clear_line,
    current_line,
    detect_kind,
    list_projects,
    looks_like_project,
    normalize_kind,
    paths,
    pick_directory,
    rename_project,
    reveal_in_file_manager,
    set_line,
    use_folder,
    wipe_project,
)
from vertex_client import (
    VertexSettings,
    generate_image,
    infer_json,
    merge_settings,
    probe,
    save_settings,
    status as vertex_status,
)

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
RESERVED_FOLDERS = {"_style", "stages", "drafts"}
boot()

app = FastAPI(title="HeroGame Art Studio")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class VertexSettingsBody(BaseModel):
    project: str = ""
    location: str = ""
    image_location: str = ""
    text_model: str = ""
    image_model: str = ""

    def to_settings(self) -> VertexSettings:
        return VertexSettings(
            project=self.project,
            location=self.location,
            image_location=self.image_location,
            text_model=self.text_model,
            image_model=self.image_model,
        )


class InferBody(BaseModel):
    appearance: str = ""
    gear: str = ""
    kit_brief: str = ""
    description: str = ""
    keywords: str = ""
    home_stage_id: str = ""
    has_transform: bool = False
    hero_id: str = ""
    vertex: VertexSettingsBody = VertexSettingsBody()


class GenerateBody(BaseModel):
    hero_id: str
    display_name: str = ""
    visual_lock: str = ""
    slot_id: str
    prompt: str
    extra_refs: list[str] = []
    skip_auto_refs: bool = False
    cyan_key: bool = False
    home_stage_id: str = ""
    vertex: VertexSettingsBody = VertexSettingsBody()
    max_tries: int = 0


class StyleInferBody(BaseModel):
    notes: str = ""
    vertex: VertexSettingsBody = VertexSettingsBody()


class StyleGenerateBody(BaseModel):
    prompt: str
    cyan_key: bool = False
    vertex: VertexSettingsBody = VertexSettingsBody()


class StageInferBody(BaseModel):
    description: str = Field(min_length=2)
    keywords: str = ""
    terrain: str = "auto"
    stage_id: str = ""
    vertex: VertexSettingsBody = VertexSettingsBody()


class StageGenerateBody(BaseModel):
    stage_id: str
    display_name: str = ""
    prompt: str
    ref_stage_id: str = ""
    vertex: VertexSettingsBody = VertexSettingsBody()


class CommitBody(BaseModel):
    kind: str = "hero"
    hero_id: str = ""
    slot_id: str = ""
    stage_id: str = ""
    cyan_key: bool = True
    vertex: VertexSettingsBody = VertexSettingsBody()


class PackExportBody(BaseModel):
    hero_ids: list[str] = []
    stage_ids: list[str] = []
    all_committed: bool = False


class DiscardBody(BaseModel):
    kind: str = "hero"
    hero_id: str = ""
    slot_id: str = ""
    stage_id: str = ""


class VoiceSaveBody(BaseModel):
    hero_id: str
    voice: dict = {}
    has_transform: bool = False


class VoiceInferBody(BaseModel):
    hero_id: str = ""
    description: str = ""
    keywords: str = ""
    has_transform: bool = False
    voice: dict = {}
    vertex: VertexSettingsBody = VertexSettingsBody()


class TtsSpeakBody(BaseModel):
    hero_id: str
    line_id: str
    text: str = ""
    tts_voice: str = ""
    speaking_rate: float = 1.0
    pitch: float = 0.0
    voice: dict = {}
    has_transform: bool = False


class VoiceCommitBody(BaseModel):
    hero_id: str
    voice: dict = {}
    has_transform: bool = False


class HeroSaveBody(BaseModel):
    hero_id: str = ""
    appearance: str = ""
    gear: str = ""
    kit_brief: str = ""
    description: str = ""
    keywords: str = ""
    home_stage_id: str = ""
    has_transform: bool = False
    prompts: dict = {}
    fx_subjects: dict = {}
    voice: dict = {}
    display_name: str = ""


class InferSlotBody(BaseModel):
    hero_id: str
    slot_id: str
    note: str = ""
    vertex: VertexSettingsBody = VertexSettingsBody()


class SplitBody(BaseModel):
    hero_id: str
    slot_id: str
    variant: int | None = None
    # 开发者可选：对默认 5/6 帧动作条按 5 或 6 切开（模型有时只画出 5 人）
    frames: int | None = None


class PortraitSlotSpec(BaseModel):
    id: str
    title: str = ""
    frames: int | None = None
    hint: str = ""


class PortraitCreateBody(BaseModel):
    appearance: str = ""
    gear: str = ""
    portrait_id: str = ""
    display_name: str = ""
    slots: list[PortraitSlotSpec] = []


class PortraitSaveBody(BaseModel):
    portrait_id: str
    appearance: str = ""
    gear: str = ""
    display_name: str = ""
    prompts: dict[str, str] = {}


class RevealPathBody(BaseModel):
    path: str = ""
    portrait_id: str = ""
    slot_id: str = ""


class PortraitInferBody(BaseModel):
    portrait_id: str = ""
    appearance: str = ""
    gear: str = ""
    slots: list[PortraitSlotSpec] = []
    vertex: VertexSettingsBody = VertexSettingsBody()


class PortraitInferSlotBody(BaseModel):
    portrait_id: str
    slot_id: str
    note: str = ""
    vertex: VertexSettingsBody = VertexSettingsBody()


class PortraitGenerateBody(BaseModel):
    portrait_id: str
    slot_id: str
    prompt: str = ""
    display_name: str = ""
    visual_lock: str = ""
    frames: int | None = None
    vertex: VertexSettingsBody = VertexSettingsBody()
    max_tries: int = 0


class PortraitSplitBody(BaseModel):
    portrait_id: str
    slot_id: str
    frames: int | None = None
    variant: int = 0


class PortraitExportBody(BaseModel):
    portrait_id: str
    slot_id: str = ""
    strict: bool = True


class PortraitDiscardBody(BaseModel):
    portrait_id: str
    slot_id: str


class PortraitDeleteBody(BaseModel):
    portrait_id: str


class PortraitBodyScaleWorkspaceBody(BaseModel):
    portrait_id: str
    ref_slot: str = "idle"


class PortraitBodyScaleSlotBody(BaseModel):
    portrait_id: str
    slot_id: str
    ref_slot: str = "idle"
    force: bool = False


class PortraitBodyScaleSaveBody(BaseModel):
    portrait_id: str
    slot_id: str
    ref_slot: str = "idle"
    frames: list[dict] = []
    order: list[int] | None = None


class PortraitBodyGuideBody(BaseModel):
    portrait_id: str
    body_guide_h: int | float | None = None


class PortraitUnifyBodyScaleBody(BaseModel):
    portrait_id: str
    ref_slot: str = "idle"


class UnifyBodyScaleBody(BaseModel):
    hero_id: str
    ref_slot: str = "idle"


class BodyScaleChartBody(BaseModel):
    hero_id: str
    ref_slot: str = "idle"


class BodyScaleWorkspaceBody(BaseModel):
    hero_id: str
    ref_slot: str = "idle"


class BodyScaleSlotBody(BaseModel):
    hero_id: str
    slot_id: str
    ref_slot: str = "idle"
    force_resplit: bool = False


class BodyScaleSaveBody(BaseModel):
    hero_id: str
    slot_id: str
    ref_slot: str = "idle"
    # [{ "index": 0, "scale": 1.12, "feet_dy": -4 }, ...] — index = new playback position
    frames: list[dict] = []
    # playback sequence of source frame indices (duplicates OK; omitted sources are dropped)
    order: list[int] | None = None


class BodyGuideBody(BaseModel):
    hero_id: str
    # null / omit clear → library default; otherwise 280–840 px（0.5×～1.5× of 560）
    body_guide_h: int | None = None
    sync_visual_scale: bool = True


class HeroDeleteBody(BaseModel):
    hero_id: str


class HeroRefClearBody(BaseModel):
    hero_id: str = ""


class HeroBakeSelectBody(BaseModel):
    hero_id: str = ""
    source_slot: str = ""
    crop_x: int | None = None
    crop_y: int | None = None
    crop_size: int | None = None


class StageDeleteBody(BaseModel):
    stage_id: str


class StageCollisionBody(BaseModel):
    stage_id: str
    collision: dict = {}


class StageBgmGenerateBody(BaseModel):
    stage_id: str
    bpm: int = 118
    use_image: bool = True
    vertex: VertexSettingsBody = VertexSettingsBody()


class StageBgmCommitBody(BaseModel):
    stage_id: str


class StageBgmDiscardBody(BaseModel):
    stage_id: str


class ProjectBody(BaseModel):
    name: str = ""
    folder: str = ""
    kind: str = ""


class BrowseBody(BaseModel):
    prompt: str = ""
    default: str = ""


class LineBody(BaseModel):
    kind: str = ""


def _sync_project_dirs() -> None:
    line = current_line() or detect_kind(paths.root)
    k = normalize_kind(line) if line else KIND_HEROGAME
    paths.ensure(k)
    if k == KIND_DESKPET:
        ensure_portrait_dirs()
    else:
        ensure_dirs()


def _require_product_line(kind: str) -> str:
    want = normalize_kind(kind)
    line = current_line()
    if line != want:
        raise HTTPException(
            400,
            f"当前不在「{LINE_LABELS.get(want, want)}」产品线。请先在启动页选择产品线。",
        )
    if not looks_like_project(paths.root) or detect_kind(paths.root) != want:
        raise HTTPException(400, f"请先新建或打开一个「{LINE_LABELS.get(want, want)}」工程。")
    return want


def _require_herogame() -> None:
    _require_product_line(KIND_HEROGAME)


def _require_deskpet() -> None:
    _require_product_line(KIND_DESKPET)


def _require_active_project() -> str:
    line = current_line()
    if line not in VALID_KINDS:
        raise HTTPException(400, "请先选择产品线（对战游戏 / 桌宠立绘）。")
    if not looks_like_project(paths.root) or detect_kind(paths.root) != line:
        raise HTTPException(400, f"请先新建或打开一个「{LINE_LABELS.get(line, line)}」工程。")
    return line


_sync_project_dirs()


def _safe_id(raw: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw.strip().lower()).strip("_")
    slug = slug[:48] or f"id_{int(time.time())}"
    if slug in RESERVED_FOLDERS or slug == "style":
        slug = f"item_{slug}"
    return slug


def _hero_dir(hero_id: str) -> Path:
    path = paths.studio / _safe_id(hero_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ref_photo_path(hero_id: str) -> Path:
    return paths.studio / _safe_id(hero_id) / "ref_photo.png"


def _has_ref_photo(hero_id: str) -> bool:
    return _ref_photo_path(hero_id).exists()


def _ref_photo_view(hero_id: str) -> dict:
    path = _ref_photo_path(hero_id)
    if not path.exists():
        return {"url": "", "exists": False}
    return {"url": _file_url(path), "exists": True}


def _bible_path(hero_id: str) -> Path:
    return _hero_dir(hero_id) / "bible.json"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


_BIBLE_LOCKS: dict[str, threading.Lock] = {}
_BIBLE_LOCKS_GUARD = threading.Lock()
_IMAGE_SEM = threading.Semaphore(3)


def _bible_lock(hero_id: str) -> threading.Lock:
    with _BIBLE_LOCKS_GUARD:
        lock = _BIBLE_LOCKS.get(hero_id)
        if lock is None:
            lock = threading.Lock()
            _BIBLE_LOCKS[hero_id] = lock
        return lock


def _read_bible(hero_id: str) -> dict:
    return _read_json(_bible_path(hero_id))


def _write_bible(hero_id: str, data: dict) -> None:
    _write_json(_bible_path(hero_id), data)


def _sync_fighter_moves_from_bible(hero_id: str, bible: dict) -> None:
    """Push kit/moves into fighter.json when the hero is already playable."""
    path = fighter_path(hero_id)
    if not path.exists():
        return
    data = _read_json(path)
    if not data:
        return
    data["kit"] = bible.get("kit") or data.get("kit") or {}
    sync_moves_into_fighter(data, bible)
    data["displayName"] = bible.get("display_name") or data.get("displayName") or hero_id
    data["oneLiner"] = bible.get("one_liner") or data.get("oneLiner") or ""
    data["visualLock"] = bible.get("visual_lock") or data.get("visualLock") or ""
    _write_json(path, data)


def _has_transform(bible: dict, flag: bool | None = None) -> bool:
    if flag is not None:
        return bool(flag)
    return bool((bible.get("kit") or {}).get("transform"))


def _apply_voice(bible: dict, raw: dict | None, has_transform: bool | None = None) -> dict:
    bible["voice"] = normalize_voice(raw if raw is not None else bible.get("voice"), has_transform=_has_transform(bible, has_transform))
    return bible["voice"]


def _preserve_clone(voice: dict, previous: dict | None) -> dict:
    prev = previous or {}
    if not voice.get("clone_key") and prev.get("clone_key"):
        voice["clone_key"] = prev["clone_key"]
        voice["clone_language"] = prev.get("clone_language") or "cmn-CN"
        voice["clone_ready"] = True
    return voice


def _compose_brief(appearance: str, gear: str, kit_brief: str, description: str = "") -> str:
    parts = [p.strip() for p in (appearance, gear, kit_brief) if p and p.strip()]
    if parts:
        return "\n".join(parts)
    return (description or "").strip()


def _normalize_fx_subjects(raw: dict | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(raw, dict):
        return out
    for slot in HERO_SLOTS:
        sid = slot["id"]
        if not sid.startswith("fx_"):
            continue
        mode = str(raw.get(sid) or "projectile").strip().lower()
        if mode in FX_SUBJECT_MODES:
            out[sid] = mode
    return out


def _rewrap_fx_slot(bible: dict, slot_id: str) -> None:
    if not slot_id.startswith("fx_"):
        return
    kit = bible.get("kit") if isinstance(bible.get("kit"), dict) else {}
    mode = fx_subject_for(bible, slot_id)
    body = fx_default_body(
        slot_id,
        kit,
        display_name=str(bible.get("display_name") or ""),
        fx_subject=mode,
    )
    hero_id = str(bible.get("hero_id") or "")
    bible.setdefault("prompts", {})[slot_id] = wrap_prompt(
        slot_id,
        body,
        bible.get("visual_lock") or "",
        kit=kit,
        display_name=str(bible.get("display_name") or ""),
        has_ref_photo=_has_ref_photo(hero_id) and slot_id == "turnaround",
        fx_subject=mode,
    )


def _migrate_hero_bible(bible: dict) -> bool:
    changed = False
    prompts = bible.setdefault("prompts", {})
    if prompts.get("combo") and not str(prompts.get("combo_up") or "").strip():
        prompts["combo_up"] = prompts["combo"]
        changed = True
    kit = bible.setdefault("kit", {})
    if kit.get("combo") and not kit.get("combo_up"):
        kit["combo_up"] = kit["combo"]
        changed = True
    if not str(bible.get("appearance") or "").strip() and bible.get("description"):
        bible["appearance"] = str(bible.get("description") or "")
        changed = True
    visual = bible.get("visual_lock") or ""
    name = str(bible.get("display_name") or "")
    fx_rewritten: list[str] = []
    for slot in HERO_SLOTS:
        sid = slot["id"]
        if not sid.startswith("fx_"):
            continue
        if fx_subject_for(bible, sid) != "projectile":
            continue
        old = str(prompts.get(sid) or "")
        if not old:
            continue
        polluted = (
            "fighter's body only" in old
            or "Do NOT paint independent VFX" in old
            or "(prism, apple, gravity, meteor, etc.)" in old
            or "prism ray, seal, meteor core" in old
        )
        if not polluted:
            continue
        move_id = slot.get("move_id") or sid[3:]
        kit_line = str(kit.get(move_id) or "").strip()
        body = (
            f"Four frames of the projectile / VFX for: {kit_line}. "
            "Only the flying effect or impact core. No hero body."
            if kit_line
            else "Four frames of one flying projectile or impact core. No hero body."
        )
        prompts[sid] = wrap_prompt(
            sid, body, visual, kit=kit, display_name=name, fx_subject="projectile"
        )
        fx_rewritten.append(sid)
        changed = True
    if fx_rewritten:
        _stamp_prompt_times(bible, fx_rewritten)
    return changed


def _stamp_prompt_times(bible: dict, slot_ids: list[str]) -> None:
    times = bible.setdefault("prompt_times", {})
    now = time.time()
    for sid in slot_ids:
        times[sid] = now


def _ensure_hero_prompts(bible: dict) -> bool:
    visual = bible.get("visual_lock") or ""
    prompts = bible.setdefault("prompts", {})
    filled: list[str] = []
    hero_id = str(bible.get("hero_id") or "")
    has_photo = _has_ref_photo(hero_id) if hero_id else False
    for slot in HERO_SLOTS:
        if not str(prompts.get(slot["id"]) or "").strip():
            prompts[slot["id"]] = wrap_prompt(
                slot["id"],
                "",
                visual,
                kit=bible.get("kit") if isinstance(bible.get("kit"), dict) else None,
                display_name=str(bible.get("display_name") or ""),
                has_ref_photo=has_photo and slot["id"] == "turnaround",
                fx_subject=fx_subject_for(bible, slot["id"]),
            )
            filled.append(slot["id"])
    if filled:
        _stamp_prompt_times(bible, filled)
        return True
    return False


def _slot_default_frames(slot_id: str) -> int:
    return int(FRAME_SLOTS.get(slot_id, 1) or 1)


def _split_frames_flexible(slot_id: str) -> bool:
    """动作条允许按实图选 5 或 6 切开（新生成默认 5；旧图可能仍是 6）。"""
    if slot_id in {"turnaround"} or str(slot_id).startswith("fx_"):
        return False
    return _slot_default_frames(slot_id) >= 5


def _resolve_split_frames(slot_id: str, requested: int | None = None, saved: dict | None = None) -> int:
    default = _slot_default_frames(slot_id)
    if not _split_frames_flexible(slot_id):
        return max(1, default)
    choice = requested
    if choice is None and saved:
        for key in ("split_frames", "expected", "frame_count"):
            if saved.get(key) is not None:
                try:
                    choice = int(saved.get(key))
                    break
                except (TypeError, ValueError):
                    pass
    if choice is None:
        return max(1, default)
    choice = int(choice)
    # 4 = 2×2 宫格；5/6 = 常规动作条；身长校对可缩短到其它正整数（≤24）
    if choice in {4, 5, 6}:
        return choice
    if 1 <= choice <= 24:
        return choice
    raise HTTPException(400, "动作条只能按 4–6 帧（常规）或身长校对后的实际帧数（1–24）切分。")


def _hero_asset_view(hero_id: str, slot_id: str) -> dict:
    view = _asset_view(draft_hero_png(hero_id, slot_id), committed_hero_png(hero_id, slot_id))
    default_frames = _slot_default_frames(slot_id)
    view["slot_frames"] = default_frames
    # Prefer fighter / strip geometry (body-scale may have shortened the strip).
    try:
        view["frame_count"] = _hero_slot_frame_count(hero_id, slot_id)
    except Exception:  # noqa: BLE001
        view["frame_count"] = default_frames
    view["split_frames_flexible"] = _split_frames_flexible(slot_id)
    files = list_split_frames(hero_id, slot_id)
    source = source_hero_png(hero_id, slot_id)
    draft = draft_hero_png(hero_id, slot_id)
    # Stale check must use the original sheet used for cutting — never the packed
    # game PNG. After「覆盖入库」the game file is newer, which used to mark frames
    # stale and made「播放」auto-resplit into a new variant.
    if source.exists():
        src_for_stale: Path | None = source
    elif draft.exists():
        src_for_stale = draft
    else:
        src_for_stale = None
    stale = False
    if src_for_stale and files:
        src_m = src_for_stale.stat().st_mtime_ns
        stale = any(p.stat().st_mtime_ns < src_m for p in files)
    view["frames"] = [{"index": int(p.stem), "url": _file_url(p)} for p in files]
    view["frames_stale"] = stale
    view["cells"] = []
    view["detected"] = 0
    view["rows"] = 1
    view["split_variant"] = 0
    view["split_label"] = ""
    view["split_count"] = SPLIT_VARIANT_COUNT
    view["split_pending"] = False
    view["grid"] = ""
    saved = None if stale else load_split_layout(hero_id, slot_id)
    if saved and files:
        view["cells"] = saved.get("cells") or []
        view["detected"] = int(saved.get("detected") or len(view["cells"]))
        view["rows"] = int(saved.get("rows") or 1)
        view["grid"] = str(saved.get("grid") or "")
        view["split_variant"] = int(saved.get("variant") or 0)
        view["split_label"] = str(saved.get("variant_label") or SPLIT_VARIANT_LABELS[view["split_variant"] % SPLIT_VARIANT_COUNT])
        try:
            view["frame_count"] = _resolve_split_frames(slot_id, None, saved)
        except HTTPException:
            view["frame_count"] = len(files) or default_frames
        if "applied" in saved:
            applied = bool(saved.get("applied"))
        else:
            # Legacy layouts: if the split preview is newer than the game PNG,
            # treat it as an unwritten re-cut waiting for overwrite.
            game = game_hero_png(hero_id, slot_id)
            meta = draft_hero_frames_dir(hero_id, slot_id) / "cells.json"
            if view.get("committed") and game.exists() and meta.exists() and meta.stat().st_mtime_ns > game.stat().st_mtime_ns:
                applied = False
            else:
                applied = bool(view.get("committed"))
        view["split_pending"] = not applied
    elif (src_for_stale or work_hero_png(hero_id, slot_id)) and default_frames > 1:
        # Hero open must stay fast: do NOT run detect_strip_cells here (full-image scan
        # × every slot). Equal-width guides / fighter frame_count are enough until split.
        view["detected"] = int(len(files) or view.get("frame_count") or 0)
        view["rows"] = 1
        view["cells"] = []
    return view


def _hero_select_icon_view(hero_id: str) -> dict:
    """Derived roster-card portrait written to assets/game/heroes/{id}/select.png."""
    path = game_hero_select_png(hero_id)
    exists = path.is_file()
    meta: dict = {}
    fp = fighter_path(hero_id)
    if fp.exists():
        try:
            fighter = json.loads(fp.read_text(encoding="utf-8"))
            raw = (fighter.get("sprites") or {}).get("select")
            if isinstance(raw, dict):
                meta = raw
        except Exception:  # noqa: BLE001
            meta = {}
    url = _file_url(path) if exists else ""
    hero_dir = path.parent
    return {
        "slot_id": "select_icon",
        "committed": exists,
        "draft": False,
        "url": url,
        "committed_url": url,
        "source": str(meta.get("source") or ""),
        "committed_at": str(meta.get("committedAt") or ""),
        "width": int(meta.get("width") or 128),
        "height": int(meta.get("height") or 128),
        "game_file": str(path.relative_to(paths.game)) if exists else "",
        "reveal_path": str(path if exists else hero_dir),
    }


def _hero_assets(hero_id: str) -> dict:
    assets = {}
    for slot in HERO_SLOTS:
        view = _hero_asset_view(hero_id, slot["id"])
        if view["url"]:
            assets[slot["id"]] = view
    sel = _hero_select_icon_view(hero_id)
    if sel.get("url") or committed_hero_png(hero_id, "turnaround") or committed_hero_png(hero_id, "idle"):
        assets["select_icon"] = sel
    return assets


def _hero_progress(hero_id: str) -> dict:
    draft_n = 0
    committed_n = 0
    work_n = 0
    for slot in HERO_SLOTS:
        if draft_hero_png(hero_id, slot["id"]).exists():
            draft_n += 1
        if committed_hero_png(hero_id, slot["id"]):
            committed_n += 1
        if work_hero_png(hero_id, slot["id"]):
            work_n += 1
    total = len(HERO_SLOTS)
    return {
        "total": total,
        "draft": draft_n,
        "committed": committed_n,
        "done": work_n,
        "incomplete": work_n < total,
    }


def _hero_payload(hero_id: str, bible: dict | None = None) -> dict:
    bible = dict(bible or _read_bible(hero_id) or {})
    bible["hero_id"] = hero_id
    migrated = _migrate_hero_bible(bible)
    filled = _ensure_hero_prompts(bible)
    if migrated or filled:
        _write_bible(hero_id, bible)
    bible["voice"] = normalize_voice(bible.get("voice"), has_transform=_has_transform(bible))
    return {
        "bible": bible,
        "assets": _hero_assets(hero_id),
        "slots": HERO_SLOTS,
        "voice_assets": _voice_assets(hero_id),
        "voice_lines": VOICE_LINES,
        "progress": _hero_progress(hero_id),
        "ref_photo": _ref_photo_view(hero_id),
    }


def _iter_hero_ids() -> list[str]:
    ids: set[str] = set()
    if paths.studio.exists():
        for folder in paths.studio.iterdir():
            if folder.is_dir() and folder.name not in RESERVED_FOLDERS:
                ids.add(folder.name)
    drafts_heroes = paths.drafts / "heroes"
    if drafts_heroes.exists():
        for folder in drafts_heroes.iterdir():
            if folder.is_dir():
                ids.add(folder.name)
    return sorted(ids)


def _tts():
    try:
        from tts_client import available_voices, probe_tts, synthesize
    except ImportError as exc:
        raise HTTPException(
            500,
            "未安装 Cloud TTS 库。请在 studio 目录运行：python3 -m pip install -r requirements.txt",
        ) from exc
    return available_voices, probe_tts, synthesize


def _voice_assets(hero_id: str) -> dict:
    assets = {}
    for slot in VOICE_LINES:
        view = _asset_view(draft_voice_mp3(hero_id, slot["id"]), committed_voice_mp3(hero_id, slot["id"]))
        if view["url"]:
            assets[slot["id"]] = view
    return assets


def _slot_png(hero_id: str, slot_id: str) -> Path:
    """Legacy studio path; refs and display use committed/draft helpers."""
    return _hero_dir(hero_id) / f"{slot_id}.png"


def _style_png() -> Path:
    return paths.style_dir / "style.png"


def _stage_exists(stage_id: str) -> bool:
    sid = _safe_id(stage_id) if stage_id else ""
    if not sid:
        return False
    return (
        (paths.stages_dir / sid / "bible.json").exists()
        or (paths.game / "stages" / sid / "stage.json").exists()
        or draft_stage_png(sid).exists()
        or bool(committed_stage_png(sid))
    )


def _stage_dir(stage_id: str) -> Path:
    path = paths.stages_dir / _safe_id(stage_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stage_png(stage_id: str) -> Path:
    return paths.stages_dir / _safe_id(stage_id) / "stage.png"


def _file_url(path: Path) -> str:
    for prefix, root in (("/drafts", paths.drafts), ("/game", paths.game), ("/library", paths.studio)):
        try:
            rel = path.relative_to(root).as_posix()
            return f"{prefix}/{rel}?t={getattr(path.stat(), 'st_mtime_ns', int(path.stat().st_mtime * 1e9))}"
        except ValueError:
            continue
    raise ValueError(f"路径不在资源根下：{path}")


def _asset_view(draft: Path, committed: Path | None) -> dict:
    draft_exists = draft.exists()
    committed_exists = bool(committed and committed.exists())
    display = draft if draft_exists else committed
    return {
        "draft": draft_exists,
        "committed": committed_exists,
        "url": _file_url(display) if display and display.exists() else "",
        "draft_url": _file_url(draft) if draft_exists else "",
        "committed_url": _file_url(committed) if committed_exists else "",
    }


def _stage_bgm_view(stage_id: str) -> dict:
    return _asset_view(draft_stage_bgm(stage_id), game_stage_bgm(stage_id))


def _archive_if_exists(path: Path) -> None:
    if not path.exists():
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bak = path.parent / "_bak"
    bak.mkdir(parents=True, exist_ok=True)
    dest = bak / f"{path.stem}_{stamp}{path.suffix}"
    shutil.copy2(path, dest)


def _maybe_bake_select(hero_id: str, slot_id: str) -> str | None:
    if slot_id not in {"turnaround", "idle"}:
        return None
    try:
        dest = bake_hero_select_portrait(hero_id)
        return str(dest.relative_to(paths.game)) if dest else None
    except Exception:  # noqa: BLE001
        return None


def _cyan_key(png_bytes: bytes, frames: int = 1, strict: bool = False) -> bytes:
    return cyan_key_png(png_bytes, frames=frames, strict=strict)


def _add_blob(blobs: list[tuple[bytes, str]], missing: list[str], path: Path | None, label: str) -> None:
    if path and path.exists():
        blobs.append((path.read_bytes(), "image/png"))
    else:
        missing.append(label)


def _style_payload() -> dict:
    bible = _read_json(paths.style_dir / "bible.json")
    view = _asset_view(draft_style_png(), committed_style_png())
    return {
        "locked": view["committed"],
        "visual_lock": bible.get("visual_lock", ""),
        "prompt": bible.get("prompt") or (bible.get("prompts") or {}).get("style", ""),
        "notes": bible.get("notes", ""),
        "source": bible.get("source", ""),
        **view,
    }


def _style_is_locked() -> bool:
    return committed_style_png() is not None


def _require_style_locked() -> None:
    if not _style_is_locked():
        raise HTTPException(400, "请先在风格锚点页采用入库。一个项目只有一个风格锚点，定调后再继续。")


def _require_style_unlocked() -> None:
    if _style_is_locked():
        raise HTTPException(400, "风格锚点已入库，本项目不可再改。")


def _list_stages() -> list[dict]:
    stages = []
    seen: set[str] = set()
    for folder in sorted(paths.stages_dir.iterdir() if paths.stages_dir.exists() else []):
        if not folder.is_dir():
            continue
        seen.add(folder.name)
        bible = _read_json(folder / "bible.json")
        view = _asset_view(draft_stage_png(folder.name), committed_stage_png(folder.name))
        stages.append(
            {
                "stage_id": folder.name,
                "display_name": bible.get("display_name") or folder.name,
                "visual": bible.get("visual", ""),
                **view,
            }
        )
    game_stages = paths.game / "stages"
    if game_stages.exists():
        for folder in sorted(game_stages.iterdir()):
            if not folder.is_dir() or folder.name in seen:
                continue
            bible = _read_json(folder / "stage.json")
            view = _asset_view(draft_stage_png(folder.name), committed_stage_png(folder.name))
            stages.append(
                {
                    "stage_id": folder.name,
                    "display_name": bible.get("displayName") or folder.name,
                    "visual": bible.get("visual", ""),
                    **view,
                }
            )
    return stages


def _clear_score(hero_id: str, slot_id: str) -> None:
    draft_hero_png(hero_id, slot_id).with_suffix(".score.json").unlink(missing_ok=True)
    (_hero_dir(hero_id) / f"{slot_id}.score.json").unlink(missing_ok=True)


def _save_draft(
    dest: Path,
    slot: dict,
    prompt: str,
    blobs: list[tuple[bytes, str]],
    settings: VertexSettings,
    reference_labels: list[str] | None = None,
) -> tuple[bytes, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    image_bytes, note = generate_image(
        prompt=prompt,
        reference_blobs=blobs,
        aspect_ratio=slot["aspect"],
        image_size=slot["size"],
        settings=settings,
        reference_labels=reference_labels,
    )
    slot_id = str(slot.get("id") or "")
    frames = FRAME_SLOTS.get(slot_id, 1)
    if slot_id.startswith("fx_") and frames > 1:
        buf = BytesIO()
        scrub_panel_borders(Image.open(BytesIO(image_bytes)).convert("RGBA"), frames=frames).save(buf, format="PNG")
        image_bytes = buf.getvalue()
    dest.write_bytes(image_bytes)
    return image_bytes, note


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


def _serve_under(root: Path, rel: str) -> FileResponse:
    base = root.resolve()
    target = (base / rel).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise HTTPException(403, "路径越界") from exc
    if not target.is_file():
        raise HTTPException(404, "没有这个文件")
    # URLs are busted with ?t=mtime_ns — allow browser cache across hero switches.
    return FileResponse(
        target,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app.get("/drafts/{path:path}")
def serve_drafts(path: str) -> FileResponse:
    return _serve_under(paths.drafts, path)


@app.get("/game/{path:path}")
def serve_game(path: str) -> FileResponse:
    return _serve_under(paths.game, path)


@app.get("/library/{path:path}")
def serve_library(path: str) -> FileResponse:
    return _serve_under(paths.studio, path)


@app.get("/api/projects")
def get_projects(kind: str = "") -> dict:
    k = normalize_kind(kind) if kind else (current_line() or "")
    return list_projects(kind=k or None)


@app.post("/api/line")
def api_set_line(body: LineBody) -> dict:
    try:
        payload = set_line(body.kind)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _sync_project_dirs()
    out = {
        "ok": True,
        "line": payload.get("line"),
        "line_label": payload.get("line_label"),
        "has_project": bool(payload.get("has_project") and payload.get("root")),
        "workspace": {
            "root": payload.get("root") or "",
            "name": payload.get("name") or "",
            "kind": payload.get("kind") or payload.get("line") or "",
            "line": payload.get("line") or "",
            "line_label": payload.get("line_label") or "",
        },
        "projects": payload.get("projects") or [],
    }
    if out["has_project"] and out["workspace"]["kind"] == KIND_HEROGAME:
        ensure_dirs()
        refresh_index()
        out["style"] = _style_payload()
        out["stages"] = _list_stages()
    elif out["has_project"] and out["workspace"]["kind"] == KIND_DESKPET:
        ensure_portrait_dirs()
        out["style"] = _style_payload()
        out["stages"] = []
    else:
        out["style"] = {"locked": False, "prompt": "", "visual_lock": "", "url": "", "notes": ""}
        out["stages"] = []
    return out


@app.post("/api/line/clear")
def api_clear_line() -> dict:
    clear_line()
    return {"ok": True, "line": "", "has_project": False, "projects": []}


@app.post("/api/projects/browse")
def api_browse_project(body: BrowseBody) -> dict:
    line = current_line()
    label = LINE_LABELS.get(line, "工程")
    prompt = body.prompt or f"选择{label}文件夹"
    try:
        folder = pick_directory(prompt, body.default)
    except Exception as exc:
        raise HTTPException(400, f"无法打开系统文件夹窗口：{exc}") from exc
    return {"ok": bool(folder), "folder": folder}


@app.post("/api/projects/use")
def api_use_project(body: ProjectBody) -> dict:
    kind = body.kind or current_line()
    if not kind:
        raise HTTPException(400, "请先选择产品线（对战游戏 / 桌宠立绘）。")
    try:
        payload = use_folder(body.folder, body.name, kind=kind)
    except (ValueError, FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc
    _sync_project_dirs()
    listed = list_projects(kind=normalize_kind(kind))
    out = {
        "ok": True,
        "created": bool(payload.get("created")),
        **listed,
        "style": _style_payload(),
        "stages": _list_stages() if normalize_kind(kind) == KIND_HEROGAME else [],
    }
    if normalize_kind(kind) == KIND_HEROGAME:
        refresh_index()
    return out


@app.post("/api/projects/rename")
def api_rename_project(body: ProjectBody) -> dict:
    try:
        rename_project(body.name)
    except (ValueError, FileNotFoundError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, **list_projects(kind=current_line() or None)}


@app.post("/api/projects/wipe")
def api_wipe_project(body: ProjectBody) -> dict:
    try:
        result = wipe_project(body.folder)
    except (ValueError, FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc
    if result.get("stayed"):
        _sync_project_dirs()
        refresh_index()
        return {
            "ok": True,
            **result,
            "style": _style_payload(),
            "stages": _list_stages(),
        }
    return {"ok": True, **result}


@app.get("/api/health")
def health() -> dict:
    info = vertex_status()
    line = current_line()
    listed = list_projects(kind=line or None)
    info["line"] = line
    info["line_label"] = LINE_LABELS.get(line, "")
    info["has_project"] = bool(listed.get("has_project"))
    info["needs_gate"] = not bool(line)
    info["slots"] = HERO_SLOTS
    info["style_slot"] = STYLE_SLOT
    info["stage_slot"] = STAGE_SLOT
    info["voice_lines"] = VOICE_LINES
    info["style"] = _style_payload() if listed.get("has_project") else {
        "locked": False, "prompt": "", "visual_lock": "", "url": "", "notes": ""
    }
    info["stages"] = _list_stages() if line == KIND_HEROGAME and listed.get("has_project") else []
    info["workspace"] = listed["active"]
    info["projects"] = listed["projects"]
    info["product_lines"] = [
        {"id": KIND_HEROGAME, "label": LINE_LABELS[KIND_HEROGAME], "modes": ["style", "stages", "heroes"]},
        {"id": KIND_DESKPET, "label": LINE_LABELS[KIND_DESKPET], "modes": ["style", "portraits"]},
    ]
    info["refs"] = {
        "style": "一个项目只有一个风格锚点。采用入库后定调，不可再改。",
        "turnaround": "可上传真人参考图。生成三视图时会优先按脸与体态对齐成像素角色。",
        "extra": "对战与桌宠工程彻底隔离；请先选产品线再打开对应工程。",
        "stage": "地图只给对战舞台用，英雄套图不参考地图。",
    }
    return info


@app.post("/api/settings")
def write_settings(body: VertexSettingsBody) -> dict:
    saved = save_settings(body.to_settings(), line=current_line())
    return {"ok": True, "settings": saved.__dict__, "line": current_line()}


@app.post("/api/test-auth")
def test_auth(body: VertexSettingsBody) -> dict:
    result = probe(body.to_settings())
    project = (result.get("settings") or {}).get("project") or body.project or ""
    try:
        _voices, probe_tts, _synth = _tts()
        result.setdefault("checks", {})["tts"] = probe_tts(project)
    except HTTPException as exc:
        result.setdefault("checks", {})["tts"] = {"ok": False, "detail": str(exc.detail)}
    return result


@app.get("/api/style")
def get_style() -> dict:
    _require_active_project()
    return {"style": _style_payload(), "slot": STYLE_SLOT}


@app.post("/api/style/infer")
def infer_style(body: StyleInferBody) -> dict:
    _require_active_project()
    _require_style_unlocked()
    line = current_line() or detect_kind(paths.root)
    notes = (body.notes or "").strip()
    if normalize_product_line(line) == KIND_DESKPET:
        user = (
            f"风格意向（必须优先落实，不要套对战格斗模板）：{notes or '（未写备注：请设计 3 个原创桌宠/立绘示范小人，宫崎骏式奇幻色彩 + 圆润饱满像素，不要格斗角色）'}\n"
            "请写出桌宠/立绘风格锚点图的英文生图提示词。"
        )
    else:
        user = (
            f"补充备注：{notes or '（无，按默认三示范格斗角色出风格锚点）'}\n"
            "请写出风格锚点图的提示词。"
        )
    try:
        data = json.loads(infer_json(style_infer_system(line), user, body.vertex.to_settings()))
    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"推理结果不是合法 JSON：{exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc

    visual = data.get("visual_lock") or ""
    prompt = wrap_prompt("style", str(data.get("prompt") or ""), visual, product_line=line)
    bible = _read_json(paths.style_dir / "bible.json")
    bible.update(
        {
            "visual_lock": visual,
            "prompt": prompt,
            "notes": body.notes,
            "source": bible.get("source") or "generated",
        }
    )
    _write_json(paths.style_dir / "bible.json", bible)
    return {"style": _style_payload(), "slot": STYLE_SLOT}


@app.post("/api/style/generate")
def generate_style(body: StyleGenerateBody) -> dict:
    _require_active_project()
    _require_style_unlocked()
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(400, "提示词是空的。")
    dest = draft_style_png()
    try:
        with _IMAGE_SEM:
            _save_draft(
                dest=dest,
                slot=STYLE_SLOT,
                prompt=prompt,
                blobs=[],
                settings=body.vertex.to_settings(),
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc
    bible = _read_json(paths.style_dir / "bible.json")
    bible["prompt"] = prompt
    bible["source"] = "generated"
    _write_json(paths.style_dir / "bible.json", bible)
    return {"style": _style_payload(), "slot": STYLE_SLOT, "draft": True}


@app.post("/api/style/upload")
async def upload_style(file: UploadFile = File(...)) -> dict:
    _require_style_unlocked()
    raw = await file.read()
    try:
        im = Image.open(BytesIO(raw)).convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"无法读取图片：{exc}") from exc
    dest = draft_style_png()
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, format="PNG")
    bible = _read_json(paths.style_dir / "bible.json")
    bible["source"] = "upload"
    _write_json(paths.style_dir / "bible.json", bible)
    return {"style": _style_payload(), "slot": STYLE_SLOT, "draft": True}


@app.get("/api/stages")
def list_stages() -> dict:
    _require_herogame()
    return {"stages": _list_stages(), "slot": STAGE_SLOT}


@app.get("/api/stages/{stage_id}")
def get_stage(stage_id: str) -> dict:
    stage_id = _safe_id(stage_id)
    folder = paths.stages_dir / stage_id
    bible = _read_json(folder / "bible.json")
    view = _asset_view(draft_stage_png(stage_id), committed_stage_png(stage_id))
    if not bible and not view["draft"] and not view["committed"]:
        raise HTTPException(404, "还没有这张地图。")
    if not bible:
        manifest = _read_json(paths.game / "stages" / stage_id / "stage.json")
        bible = {
            "stage_id": stage_id,
            "display_name": manifest.get("displayName") or stage_id,
            "visual": manifest.get("visual") or "",
            "description": manifest.get("visual") or "",
            "keywords": "",
            "prompt": "",
        }
    bible.setdefault("stage_id", stage_id)
    manifest = _read_json(paths.game / "stages" / stage_id / "stage.json")
    collision = sanitize_stage_collision(bible.get("collision") or manifest.get("collision"))
    bible["collision"] = collision
    bgm_meta = manifest.get("bgmMeta") if isinstance(manifest.get("bgmMeta"), dict) else {}
    return {
        "bible": bible,
        "slot": STAGE_SLOT,
        "asset": view if (view["url"]) else None,
        "bgm_asset": _stage_bgm_view(stage_id),
        "bgm_meta": bgm_meta,
        "collision": collision,
    }


@app.post("/api/stages/collision")
def save_stage_collision(body: StageCollisionBody) -> dict:
    stage_id = _safe_id(body.stage_id)
    if not stage_id:
        raise HTTPException(400, "没有 stage_id。")
    collision = sanitize_stage_collision(body.collision)
    folder = _stage_dir(stage_id)
    bible = _read_json(folder / "bible.json")
    if not bible:
        bible = {"stage_id": stage_id, "display_name": stage_id}
    bible["collision"] = collision
    if bible.get("prompt"):
        bible["prompt"] = with_stage_terrain_prompt(str(bible.get("prompt") or ""), collision)
    _write_json(folder / "bible.json", bible)
    manifest_path = paths.game / "stages" / stage_id / "stage.json"
    committed = False
    if manifest_path.exists():
        manifest = _read_json(manifest_path) or {"id": stage_id, "file": "stage.png"}
        manifest["collision"] = collision
        #  bump 时间戳，对战端按 committedAt 强刷资源，避免旧碰撞缓存
        manifest["committedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _write_json(manifest_path, manifest)
        try:
            from game_assets import refresh_index

            refresh_index()
        except Exception:
            pass
        committed = True
    return {
        "ok": True,
        "stage_id": stage_id,
        "collision": collision,
        "prompt": bible.get("prompt") or "",
        "committed": committed,
    }


@app.post("/api/stages/bgm/generate")
def generate_stage_bgm_route(body: StageBgmGenerateBody) -> dict:
    stage_id = _safe_id(body.stage_id)
    if not stage_id or not _stage_exists(stage_id):
        raise HTTPException(400, "先打开或创建一张地图。")
    bible = _read_json(_stage_dir(stage_id) / "bible.json")
    manifest = _read_json(paths.game / "stages" / stage_id / "stage.json")
    display_name = bible.get("display_name") or manifest.get("displayName") or stage_id
    visual = bible.get("visual") or bible.get("description") or manifest.get("visual") or ""
    if not visual.strip():
        raise HTTPException(400, "先写地图描述或 visual，再生成 BGM。")
    image_bytes = None
    image_mime = "image/png"
    if body.use_image:
        from bgm_client import load_stage_reference_png

        ref = load_stage_reference_png(stage_id)
        if ref:
            image_bytes, image_mime = ref
    try:
        from bgm_client import generate_stage_bgm

        mp3, note, meta = generate_stage_bgm(
            display_name=display_name,
            visual=visual,
            bpm=body.bpm,
            image_bytes=image_bytes,
            image_mime=image_mime,
            settings=body.vertex.to_settings(),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc
    dest = draft_stage_bgm(stage_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(mp3)
    meta_path = dest.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "stage_id": stage_id,
        "bgm_asset": _stage_bgm_view(stage_id),
        "bgm_meta": meta,
        "note": note,
        "prompt": meta.get("prompt") or "",
    }


@app.post("/api/stages/bgm/commit")
def commit_stage_bgm_route(body: StageBgmCommitBody) -> dict:
    stage_id = _safe_id(body.stage_id)
    src = draft_stage_bgm(stage_id)
    if not src.exists():
        raise HTTPException(400, "没有 BGM 草稿。请先生成。")
    manifest_path = stage_manifest_path(stage_id)
    if not manifest_path.exists():
        raise HTTPException(400, "地图还没入库。请先把 stage.png 采用入库，再提交 BGM。")
    meta_path = src.with_suffix(".meta.json")
    meta: dict = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
    dest = game_stage_bgm(stage_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        _archive_if_exists(dest)
    shutil.copy2(src, dest)
    src.unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)
    manifest = upsert_stage_bgm(stage_id, meta)
    return {
        "ok": True,
        "stage_id": stage_id,
        "bgm_asset": _stage_bgm_view(stage_id),
        "bgm_meta": manifest.get("bgmMeta") or {},
        "game_file": f"stages/{stage_id}/bgm.mp3",
    }


@app.post("/api/stages/bgm/discard")
def discard_stage_bgm_route(body: StageBgmDiscardBody) -> dict:
    stage_id = _safe_id(body.stage_id)
    draft_stage_bgm(stage_id).unlink(missing_ok=True)
    draft_stage_bgm(stage_id).with_suffix(".meta.json").unlink(missing_ok=True)
    return {"ok": True, "stage_id": stage_id, "bgm_asset": _stage_bgm_view(stage_id)}


@app.post("/api/stages/delete")
def delete_stage(body: StageDeleteBody) -> dict:
    stage_id = _safe_id(body.stage_id)
    if not stage_id:
        raise HTTPException(400, "没有 stage_id。")
    studio_dir = paths.stages_dir / stage_id
    draft_dir = paths.drafts / "stages" / stage_id
    game_dir = paths.game / "stages" / stage_id
    if not studio_dir.exists() and not draft_dir.exists() and not game_dir.exists():
        raise HTTPException(404, "还没有这张地图。")
    if studio_dir.exists() and studio_dir.is_dir():
        shutil.rmtree(studio_dir)
    if draft_dir.exists() and draft_dir.is_dir():
        shutil.rmtree(draft_dir)
    remove_stage(stage_id)
    return {"ok": True, "stage_id": stage_id, "stages": _list_stages()}


@app.post("/api/stages/infer")
def infer_stage(body: StageInferBody) -> dict:
    _require_herogame()
    _require_style_locked()
    terrain = body.terrain.strip().lower() if body.terrain else "auto"
    if terrain not in STAGE_TERRAIN_HINTS:
        terrain = "auto"
    keep_id = _safe_id(body.stage_id) if body.stage_id.strip() else ""
    if keep_id and not _stage_exists(keep_id):
        keep_id = ""
    existing = _read_json(paths.stages_dir / keep_id / "bible.json") if keep_id else {}
    if keep_id and not existing:
        manifest = _read_json(paths.game / "stages" / keep_id / "stage.json")
        if manifest:
            existing = {
                "stage_id": keep_id,
                "display_name": manifest.get("displayName") or keep_id,
                "visual": manifest.get("visual") or "",
            }
    user = (
        f"地图描述：{body.description.strip()}\n"
        f"关键词：{body.keywords.strip() or '（无）'}\n"
        f"地形意向：{terrain}\n"
        f"{STAGE_TERRAIN_HINTS[terrain]}\n"
    )
    if keep_id:
        user += (
            f"这是对已有地图 `{keep_id}`（{existing.get('display_name') or keep_id}）的改稿，不是新地图。"
            f"必须沿用同一个 stage_id。中文名可以微调。\n"
            f"原场景要点：{existing.get('visual') or existing.get('description') or '（无）'}\n"
        )
    user += (
        "请推理一张可复用对战地图的提示词，并给出与画面一致的 collision。"
        "高台和凹地必须画进场景，不要用色块。凹地要有底、可站立。不要画角色。"
    )
    try:
        data = json.loads(infer_json(STAGE_INFER_SYSTEM, user, body.vertex.to_settings()))
    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"推理结果不是合法 JSON：{exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc

    stage_id = keep_id or _safe_id(str(data.get("stage_id") or body.description))
    bible = dict(existing) if existing else {}
    bible.update(data if isinstance(data, dict) else {})
    bible["stage_id"] = stage_id
    if existing.get("display_name") and not str(bible.get("display_name") or "").strip():
        bible["display_name"] = existing["display_name"]
    bible["description"] = body.description
    bible["keywords"] = body.keywords
    bible["terrain"] = terrain
    bible["collision"] = sanitize_stage_collision(bible.get("collision"))
    bible["prompt"] = with_stage_terrain_prompt(
        wrap_prompt("stage", str(bible.get("prompt") or "")),
        bible["collision"],
    )
    _write_json(_stage_dir(stage_id) / "bible.json", bible)
    view = _asset_view(draft_stage_png(stage_id), committed_stage_png(stage_id))
    return {
        "bible": bible,
        "slot": STAGE_SLOT,
        "asset": view if view["url"] else None,
        "updated": bool(keep_id),
        "stages": _list_stages(),
    }


@app.post("/api/stages/generate")
def generate_stage(body: StageGenerateBody) -> dict:
    _require_herogame()
    _require_style_locked()
    if not body.prompt.strip():
        raise HTTPException(400, "提示词是空的。")
    stage_id = _safe_id(body.stage_id)
    blobs: list[tuple[bytes, str]] = []
    missing: list[str] = []
    used: list[str] = []
    before = len(blobs)
    _add_blob(blobs, missing, committed_style_png(), "style")
    if len(blobs) > before:
        used.append("style")
    if body.ref_stage_id:
        before = len(blobs)
        _add_blob(blobs, missing, committed_stage_png(body.ref_stage_id), body.ref_stage_id)
        if len(blobs) > before:
            used.append(body.ref_stage_id)
    dest = draft_stage_png(stage_id)
    bible = _read_json(_stage_dir(stage_id) / "bible.json")
    collision = sanitize_stage_collision(bible.get("collision"))
    prompt = with_stage_terrain_prompt(body.prompt.strip(), collision)
    try:
        with _IMAGE_SEM:
            _save_draft(
                dest=dest,
                slot=STAGE_SLOT,
                prompt=prompt,
                blobs=blobs,
                settings=body.vertex.to_settings(),
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc

    bible["stage_id"] = stage_id
    if body.display_name:
        bible["display_name"] = body.display_name
    bible["collision"] = collision
    bible["prompt"] = prompt
    _write_json(_stage_dir(stage_id) / "bible.json", bible)
    return {
        "bible": bible,
        "slot": STAGE_SLOT,
        "asset": _asset_view(dest, committed_stage_png(stage_id)),
        "used_refs": used,
        "missing_refs": missing,
        "stages": _list_stages(),
        "draft": True,
    }


@app.get("/api/heroes")
def list_heroes() -> dict:
    _require_herogame()
    heroes = []
    for hero_id in _iter_hero_ids():
        bible = _read_bible(hero_id)
        progress = _hero_progress(hero_id)
        if not bible and progress["done"] == 0:
            continue
        thumbs = {}
        sel_path = game_hero_select_png(hero_id)
        if sel_path.is_file():
            thumbs["select_icon"] = _file_url(sel_path)
        for slot in HERO_SLOTS:
            png = work_hero_png(hero_id, slot["id"])
            if png:
                thumbs[slot["id"]] = _file_url(png)
        heroes.append(
            {
                "hero_id": hero_id,
                "display_name": (bible or {}).get("display_name") or hero_id,
                "one_liner": (bible or {}).get("one_liner", ""),
                "thumbs": thumbs,
                "progress": progress,
            }
        )
    heroes.sort(key=lambda h: (-int((h.get("progress") or {}).get("done") or 0), h["hero_id"]))
    return {"heroes": heroes}


@app.get("/api/heroes/{hero_id}")
def get_hero(hero_id: str) -> dict:
    hero_id = _safe_id(hero_id)
    bible = _read_bible(hero_id)
    has_art = any(work_hero_png(hero_id, slot["id"]) for slot in HERO_SLOTS)
    if not bible and not has_art:
        raise HTTPException(404, "还没有这个英雄的设定。")
    if not bible:
        bible = {"hero_id": hero_id, "display_name": hero_id, "prompts": {}, "description": ""}
        _write_bible(hero_id, bible)
    return _hero_payload(hero_id, bible)


@app.post("/api/heroes/save")
def save_hero(body: HeroSaveBody) -> dict:
    if not (body.hero_id or "").strip() and len(_compose_brief(body.appearance, body.gear, body.kit_brief, body.description)) < 2:
        raise HTTPException(400, "先写人物形象，或打开一个已有英雄。")
    hero_id = _safe_id(body.hero_id) if body.hero_id else _safe_id(body.appearance or body.description)
    bible = _read_bible(hero_id) or {"hero_id": hero_id}
    bible["hero_id"] = hero_id
    if body.appearance.strip():
        bible["appearance"] = body.appearance.strip()
    if body.gear.strip():
        bible["gear"] = body.gear.strip()
    if body.kit_brief.strip():
        bible["kit_brief"] = body.kit_brief.strip()
    composed = _compose_brief(
        body.appearance or bible.get("appearance", ""),
        body.gear or bible.get("gear", ""),
        body.kit_brief or bible.get("kit_brief", ""),
        body.description,
    )
    if composed:
        bible["description"] = composed
    bible["keywords"] = body.keywords
    bible["home_stage_id"] = _safe_id(body.home_stage_id) if body.home_stage_id else bible.get("home_stage_id") or ""
    if body.display_name:
        bible["display_name"] = body.display_name
    if not bible.get("display_name"):
        bible["display_name"] = (bible.get("description") or hero_id)[:24]
    if body.prompts:
        prompts = bible.get("prompts") or {}
        changed: list[str] = []
        for slot in HERO_SLOTS:
            if slot["id"] in body.prompts:
                new = str(body.prompts[slot["id"]] or "")
                if new != str(prompts.get(slot["id"]) or ""):
                    changed.append(slot["id"])
                prompts[slot["id"]] = new
        bible["prompts"] = prompts
        if changed:
            _stamp_prompt_times(bible, changed)
    prev_fx = _normalize_fx_subjects(bible.get("fx_subjects"))
    next_fx = _normalize_fx_subjects(body.fx_subjects) if body.fx_subjects else prev_fx
    if body.fx_subjects:
        bible["fx_subjects"] = next_fx
        rewrapped: list[str] = []
        for sid, mode in next_fx.items():
            if prev_fx.get(sid, "projectile") != mode:
                _rewrap_fx_slot(bible, sid)
                rewrapped.append(sid)
        if rewrapped:
            _stamp_prompt_times(bible, rewrapped)
    prev_voice = bible.get("voice") or {}
    if body.voice:
        _apply_voice(bible, body.voice, body.has_transform)
        _preserve_clone(bible["voice"], prev_voice)
        _preserve_clone(bible["voice"], body.voice)
    _write_bible(hero_id, bible)
    return _hero_payload(hero_id, bible)


@app.post("/api/infer")
def infer(body: InferBody) -> dict:
    _require_herogame()
    _require_style_locked()
    appearance = (body.appearance or "").strip()
    gear = (body.gear or "").strip()
    kit_brief = (body.kit_brief or "").strip()
    description = _compose_brief(appearance, gear, kit_brief, body.description)
    if len(description) < 2:
        raise HTTPException(400, "请填写人物形象、武器配饰、技能机制。")
    user = (
        f"人物形象：{appearance or description}\n"
        f"人物武器配饰：{gear or '（未单列，见形象）'}\n"
        f"人物技能机制：{kit_brief or '（未单列，见形象）'}\n"
        "不要设计地图槽。出场/战败/战胜也是 5 帧青屏动作条，不要背景。"
        "请按角色动作槽 + 4 个 fx_* 弹道槽写出严谨生图提示词，并填写 moves 数值（effect / mechanic / ailment / projectile）。同一英雄四招 mechanic 必须不同。不要为燃烧/冰冻/中毒增加贴图槽。"
    )
    try:
        raw = infer_json(INFER_SYSTEM, user, body.vertex.to_settings())
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"推理结果不是合法 JSON：{exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc

    hero_id = _safe_id(body.hero_id) if body.hero_id else _safe_id(str(data.get("hero_id") or appearance or description))
    existing = _read_bible(hero_id)
    data["hero_id"] = hero_id
    if existing.get("display_name") and not data.get("display_name"):
        data["display_name"] = existing["display_name"]
    slots_in = data.get("slots") or {}
    if slots_in.get("combo") and not slots_in.get("combo_up"):
        slots_in["combo_up"] = slots_in["combo"]
    wrapped = {}
    visual = data.get("visual_lock") or existing.get("visual_lock") or ""
    has_photo = _has_ref_photo(hero_id)
    for slot in HERO_SLOTS:
        body_prompt = slots_in.get(slot["id"]) or ""
        wrapped[slot["id"]] = wrap_prompt(
            slot["id"],
            str(body_prompt),
            visual,
            kit=data.get("kit") if isinstance(data.get("kit"), dict) else None,
            display_name=str(data.get("display_name") or ""),
            has_ref_photo=has_photo and slot["id"] == "turnaround",
            fx_subject=fx_subject_for(data, slot["id"]),
        )
    data["prompts"] = wrapped
    zh_in = data.get("slots_zh") if isinstance(data.get("slots_zh"), dict) else {}
    data["prompts_zh"] = {
        slot["id"]: str(zh_in.get(slot["id"]) or "").strip() or slot_zh_fallback(slot)
        for slot in HERO_SLOTS
    }
    _stamp_prompt_times(data, [slot["id"] for slot in HERO_SLOTS])
    data["appearance"] = appearance or existing.get("appearance") or ""
    data["gear"] = gear or existing.get("gear") or ""
    data["kit_brief"] = kit_brief or existing.get("kit_brief") or ""
    data["description"] = description
    data["keywords"] = body.keywords
    data["home_stage_id"] = _safe_id(body.home_stage_id) if body.home_stage_id else ""
    _apply_voice(data, data.get("voice"), False)
    _preserve_clone(data["voice"], (existing or {}).get("voice"))
    kit = data.get("kit") if isinstance(data.get("kit"), dict) else {}
    data["moves"] = normalize_moves(data.get("moves") if isinstance(data.get("moves"), dict) else None, kit)
    _write_bible(hero_id, data)
    _sync_fighter_moves_from_bible(hero_id, data)
    return _hero_payload(hero_id, data)


@app.post("/api/infer-slot")
def infer_slot(body: InferSlotBody) -> dict:
    _require_style_locked()
    if body.slot_id not in {s["id"] for s in HERO_SLOTS}:
        raise HTTPException(400, f"未知槽位 {body.slot_id}")
    hero_id = _safe_id(body.hero_id)
    bible = _read_bible(hero_id)
    if not bible:
        raise HTTPException(400, "还没有这个英雄。先写出关键帧提示词。")
    slot = SLOT_BY_ID[body.slot_id]
    visual = bible.get("visual_lock") or ""
    fx_mode = fx_subject_for(bible, body.slot_id)
    prev = (bible.get("prompts") or {}).get(body.slot_id) or ""
    fx_infer_note = ""
    if body.slot_id.startswith("fx_"):
        if fx_mode == "figure":
            fx_infer_note = (
                "这一槽是体术/骑乘/冲锋类特效：画英雄本人（含坐骑如有）完成技能，"
                "单行 4 帧全身侧视朝右，禁止只画 detached 弹体。\n"
            )
        elif fx_mode == "clone":
            fx_infer_note = (
                "这一槽是分身/残影特效：画同一英雄的分身或重影，"
                "单行 4 帧全身侧视朝右。\n"
            )
        else:
            fx_infer_note = "这一槽是弹道/特效：只画该招 kit 对应的飞行物，禁止画人。\n"
    user = (
        f"人物形象：{bible.get('appearance') or bible.get('description') or ''}\n"
        f"武器配饰：{bible.get('gear') or ''}\n"
        f"技能机制：{bible.get('kit_brief') or ''}\n"
        f"visual_lock：{visual}\n"
        f"技能闸门：{json.dumps(bible.get('kit') or {}, ensure_ascii=False)}\n"
        f"fx_subjects：{json.dumps(bible.get('fx_subjects') or {}, ensure_ascii=False)}\n"
        f"要重写的槽：{body.slot_id}（{slot.get('title')}）\n"
        f"槽位要求：{slot.get('hint')}\n"
        f"旧提示词：{prev or '（无）'}\n"
        f"开发者哪里不满意（必须写进新英文提示词并改掉，禁止复读旧稿）：{body.note.strip() or '（未写，请换一套分镜，不要复读旧稿）'}\n"
        + fx_infer_note
        + "只重写这一槽的英文生图提示词。"
    )
    try:
        raw = infer_json(SLOT_INFER_SYSTEM, user, body.vertex.to_settings())
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"推理结果不是合法 JSON：{exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc
    body_prompt = str(data.get("prompt") or "").strip()
    if not body_prompt:
        raise HTTPException(502, "这一槽没有写出新提示词。")
    wrapped = wrap_prompt(
        body.slot_id,
        body_prompt,
        visual,
        developer_fix=body.note,
        kit=bible.get("kit") if isinstance(bible.get("kit"), dict) else None,
        display_name=str(bible.get("display_name") or ""),
        has_ref_photo=_has_ref_photo(hero_id) and body.slot_id == "turnaround",
        fx_subject=fx_mode,
    )
    prompts = bible.setdefault("prompts", {})
    prompts[body.slot_id] = wrapped
    note = body.note.strip()
    zh = str(data.get("prompt_zh") or "").strip() or slot_zh_fallback(slot, note, fx_subject=fx_mode)
    if note and "已按意见" not in zh and note not in zh:
        zh = f"已按意见修改：{note}。{zh}"
    bible.setdefault("prompts_zh", {})[body.slot_id] = zh
    notes = bible.setdefault("prompt_notes", {})
    if note:
        notes[body.slot_id] = note
    else:
        notes.pop(body.slot_id, None)
    _stamp_prompt_times(bible, [body.slot_id])
    _write_bible(hero_id, bible)
    payload = _hero_payload(hero_id, bible)
    payload["slot_id"] = body.slot_id
    payload["prompt"] = wrapped
    return payload


@app.post("/api/heroes/delete")
def delete_hero_draft(body: HeroDeleteBody) -> dict:
    hero_id = _safe_id(body.hero_id)
    if not hero_id:
        raise HTTPException(400, "没有 hero_id。")
    draft_dir = paths.drafts / "heroes" / hero_id
    studio_dir = paths.studio / hero_id
    if draft_dir.exists():
        shutil.rmtree(draft_dir)
    if studio_dir.exists() and studio_dir.is_dir():
        shutil.rmtree(studio_dir)
    return {"ok": True, "hero_id": hero_id, "heroes": list_heroes()["heroes"]}


@app.post("/api/generate")
def generate(body: GenerateBody) -> dict:
    _require_herogame()
    _require_style_locked()
    if body.slot_id not in {s["id"] for s in HERO_SLOTS}:
        raise HTTPException(400, f"未知槽位 {body.slot_id}")
    slot = SLOT_BY_ID[body.slot_id]
    hero_id = _safe_id(body.hero_id)
    bible = _read_bible(hero_id)
    visual = body.visual_lock or bible.get("visual_lock") or ""
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(400, "提示词是空的。")
    expected_frames = FRAME_SLOTS.get(body.slot_id, 1)
    if slot.get("kind") == "sprite" and expected_frames > 1:
        from prompts import enforce_strip_frame_count

        prompt = enforce_strip_frame_count(prompt, expected_frames)
    fx_mode = fx_subject_for(bible, body.slot_id) if body.slot_id.startswith("fx_") else "projectile"
    if body.slot_id.startswith("fx_") and fx_mode == "projectile":
        polluted = (
            "fighter's body only" in prompt
            or "Do NOT paint independent VFX" in prompt
            or "(prism, apple, gravity, meteor, etc.)" in prompt
            or "prism ray, seal, meteor core" in prompt
        )
        if polluted:
            move_id = slot.get("move_id") or body.slot_id[3:]
            kit_obj = bible.get("kit") if isinstance(bible.get("kit"), dict) else {}
            kit_line = str(kit_obj.get(move_id) or "").strip()
            body_txt = (
                f"Four frames of the projectile / VFX for: {kit_line}. Only the effect. No hero."
                if kit_line
                else "Four frames of one flying projectile or impact core. No hero."
            )
            prompt = wrap_prompt(
                body.slot_id,
                body_txt,
                visual,
                kit=kit_obj,
                display_name=str(bible.get("display_name") or ""),
                fx_subject="projectile",
            )
    if body.slot_id != "turnaround" and not committed_hero_png(hero_id, "turnaround"):
        raise HTTPException(400, "请先把人物三视图采用入库，再生成其他套图。")

    blobs: list[tuple[bytes, str]] = []
    labels: list[str] = []
    missing: list[str] = []
    used: list[str] = []

    def _push(path: Path | None, key: str, caption: str) -> None:
        before = len(blobs)
        _add_blob(blobs, missing, path, key)
        if len(blobs) > before:
            used.append(key)
            labels.append(caption)

    if not body.skip_auto_refs:
        # Character first. Style PNG last — image models copy the first picture.
        # FX projectile strips attach nothing (refs bleed people into pure VFX).
        # FX figure/clone strips need turnaround like action strips.
        fx_figure = body.slot_id.startswith("fx_") and fx_mode in {"figure", "clone"}
        if not body.slot_id.startswith("fx_") or fx_figure:
            if body.slot_id == "turnaround":
                photo = _ref_photo_path(hero_id)
                if photo.exists():
                    _push(photo, "ref_photo", REF_LABEL_PHOTO)
            ref_ids = list(slot.get("auto_refs") or [])
            if fx_figure and "turnaround" not in ref_ids:
                ref_ids = ["turnaround", *ref_ids]
            for ref_id in ref_ids:
                path = committed_hero_png(hero_id, ref_id)
                if not path and ref_id == "turnaround":
                    draft_ta = draft_hero_png(hero_id, "turnaround")
                    path = draft_ta if draft_ta.exists() else None
                caption = REF_LABEL_TURNAROUND if ref_id == "turnaround" else f"This is the {ref_id} sheet of the same hero."
                _push(path, ref_id, caption)
            for ref_id in slot.get("global_refs") or []:
                if ref_id == "style":
                    _push(committed_style_png(), "style", REF_LABEL_STYLE)

    if not body.slot_id.startswith("fx_") or fx_mode in {"figure", "clone"}:
        for extra in body.extra_refs:
            if extra in used:
                continue
            _push(committed_hero_png(hero_id, extra), extra, "Additional sheet of the same hero.")

    dest = draft_hero_png(hero_id, body.slot_id)
    settings = merge_settings(body.vertex.to_settings())
    expected = FRAME_SLOTS.get(body.slot_id, 1)
    strip = slot.get("kind") == "sprite" and expected > 1
    default_tries = 2 if strip else 1
    max_tries = body.max_tries if body.max_tries > 0 else default_tries
    max_tries = max(1, min(int(max_tries), 3))
    if body.slot_id == "turnaround":
        has_photo = "ref_photo" in used
        if has_photo:
            layout_lock = (
                "\n\nHARD LAYOUT: ONE horizontal ROW, EXACTLY 4 FULL-BODY figures of THE SAME hero. "
                "1 front, 2 three-quarter, 3 right-side, 4 back. Same costume. "
                "LIKENESS: the first attached image is a real-person reference — match that face/build "
                "in PIXEL ART (never output a photo). Costume from CHARACTER LOCK. "
                "FORBIDDEN: house-style dummy fighters, three different people, 2 rows, busts, photoreal. "
                f"{STRIP_SEPARATION}"
            )
        else:
            layout_lock = (
                "\n\nHARD LAYOUT: ONE horizontal ROW, EXACTLY 4 FULL-BODY figures of THE SAME hero. "
                "1 front, 2 three-quarter, 3 right-side, 4 back. Same costume. "
                "FORBIDDEN: house-style dummy fighters, three different people, 2 rows, busts. "
                f"{STRIP_SEPARATION} "
                "There is NO style image attached. Draw from CHARACTER LOCK only."
            )
        style_visual = (_style_payload().get("visual_lock") or "").strip()
        if style_visual:
            layout_lock = (
                f"\n\nPIXEL LANGUAGE (text only, no dummy characters to copy): {style_visual}"
                + layout_lock
            )
        if has_photo and "NO character photo is attached" in prompt:
            prompt = prompt.replace(
                "NO character photo is attached. Invent this fighter from CHARACTER LOCK only.",
                "A likeness REFERENCE PHOTO is attached first. Match that person in pixel art.",
                1,
            )
    elif body.slot_id.startswith("fx_"):
        if fx_mode == "figure":
            layout_lock = (
                f"\n\nHARD LAYOUT: ONE horizontal ROW, EXACTLY {expected} FULL-BODY figures of THE SAME hero performing the skill. "
                "Side profile facing RIGHT. Include mount if kit describes riding. "
                "FORBIDDEN: detached projectile-only frames, black/gray panel borders, vertical divider bars. "
                "Separate cells with empty #00FFFF only — never draw gutters. "
                "Adjacent frames are in-betweens of ONE charge / strike / trample arc. "
                f"{FX_FIGURE_STRIP_SEPARATION}"
            )
        elif fx_mode == "clone":
            layout_lock = (
                f"\n\nHARD LAYOUT: ONE horizontal ROW, EXACTLY {expected} clone/afterimage copies of THE SAME hero. "
                "Side profile facing RIGHT. "
                "FORBIDDEN: unrelated projectiles with no body, black/gray panel borders, three different people. "
                "Separate cells with empty #00FFFF only — never draw gutters. "
                f"{FX_CLONE_STRIP_SEPARATION}"
            )
        else:
            layout_lock = (
                f"\n\nHARD LAYOUT: ONE horizontal ROW, EXACTLY {expected} PROJECTILE/VFX frames. "
                "FORBIDDEN: any human figure, face, costume, full-body pose. "
                "FORBIDDEN: black/gray panel borders, vertical divider bars, comic frames. "
                "Separate cells with empty #00FFFF only — never draw gutters. "
                "Count flying effects, not people. "
                f"{FX_STRIP_SEPARATION}"
            )
    elif strip:
        layout_lock = (
            f"\n\nHARD LAYOUT: ONE horizontal ROW, EXACTLY {expected} FULL-BODY figures, no more no less. "
            f"FORBIDDEN: 2 rows, 2x5 contact sheet, bust/head row, 8 or 10 clones, or {expected + 1} people. "
            "Count the people. Adjacent frames are in-betweens of ONE action. "
            "Limbs travel on arcs (opposite legs / high passing foot / weapon swing). "
            "Identical mid-pose clones = fail. "
            "Adjacent silhouettes must differ at thumbnail size "
            "(legs, torso, and weapon — not a frozen body plus a tiny sword wiggle). "
            "Cell widths may differ: lying down or full extension needs a WIDER cell; "
            "never crop a body to 1/N of the strip. "
            f"{STRIP_SEPARATION}"
        )
    else:
        layout_lock = ""
    attempts = 0
    try:
        while True:
            attempts += 1
            use_prompt = prompt + layout_lock
            if attempts > 1:
                if body.slot_id == "turnaround":
                    retry = TURNAROUND_RETRY
                elif body.slot_id.startswith("fx_"):
                    if fx_mode == "figure":
                        retry = FX_FIGURE_STRIP_RETRY.format(n=expected)
                    elif fx_mode == "clone":
                        retry = FX_CLONE_STRIP_RETRY.format(n=expected)
                    else:
                        retry = FX_STRIP_RETRY.format(n=expected)
                else:
                    retry = STRIP_RETRY.format(n=expected)
                use_prompt += f"\n\n{retry}"
            with _IMAGE_SEM:
                _save_draft(
                    dest=dest,
                    slot=slot,
                    prompt=use_prompt,
                    blobs=blobs,
                    settings=settings,
                    reference_labels=labels,
                )
            if attempts >= max_tries or not strip:
                break
            layout = detect_strip_cells(Image.open(dest), expected)
            count_ok = layout.get("detected") == expected and layout.get("rows") == 1
            pipe = heuristic_score(dest.read_bytes(), slot)
            div = diversity_score(pipe)
            need = 42 if body.slot_id == "idle" else 58
            div_ok = div is None or div >= need
            if count_ok and div_ok:
                break
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc

    with _bible_lock(hero_id):
        bible = _read_bible(hero_id) or {}
        bible["hero_id"] = hero_id
        if body.display_name:
            bible["display_name"] = body.display_name
        if visual:
            bible["visual_lock"] = visual
        prompts = bible.get("prompts") or {}
        prompts[body.slot_id] = prompt
        bible["prompts"] = prompts
        _write_bible(hero_id, bible)

    dest = draft_hero_png(hero_id, body.slot_id)
    remember_split_source(hero_id, body.slot_id, dest)
    clear_split_frames(hero_id, body.slot_id)
    _clear_score(hero_id, body.slot_id)
    return {
        "hero_id": hero_id,
        "slot_id": body.slot_id,
        "url": _file_url(dest),
        "asset": _hero_asset_view(hero_id, body.slot_id),
        "used_refs": used,
        "missing_refs": missing,
        "prompt": prompt,
        "attempts": attempts,
        "image_model": settings.image_model,
        "draft": True,
    }


def _write_commit(
    src: Path,
    dest: Path,
    keyed: bool,
    frames: int = 1,
    strict: bool = False,
    pack: bool = True,
    raw: bytes | None = None,
) -> None:
    frames = max(1, int(frames or 1))
    if raw is None:
        if pack and frames > 1:
            buf = BytesIO()
            prepare_sprite_sheet(src, frames).save(buf, format="PNG")
            raw = buf.getvalue()
        else:
            raw = src.read_bytes()
    if keyed:
        raw = _cyan_key(raw, frames=frames, strict=strict)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        _archive_if_exists(dest)
    dest.write_bytes(raw)


@app.post("/api/pack/export")
def export_content_pack(body: PackExportBody) -> Response:
    """Zip committed heroes/stages from the open project. Does not touch any other game install."""
    _require_herogame()
    try:
        if body.all_committed:
            raw, filename, _meta = build_pack_zip()
        else:
            raw, filename, _meta = build_pack_zip(
                hero_ids=list(body.hero_ids or []),
                stage_ids=list(body.stage_ids or []),
            )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(
        content=raw,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@app.post("/api/commit")
def commit_asset(body: CommitBody) -> dict:
    keyed = body.cyan_key
    if body.kind == "style":
        _require_active_project()
        _require_style_unlocked()
        src = draft_style_png()
        if not src.exists():
            raise HTTPException(400, "没有风格草稿。先生成或上传，再采用入库。")
        _write_commit(src, game_style_png(), keyed=False)
        src.unlink(missing_ok=True)
        refresh_index()
        return {"kind": "style", "style": _style_payload()}

    if body.kind == "stage":
        _require_herogame()
        stage_id = _safe_id(body.stage_id)
        src = draft_stage_png(stage_id)
        if not src.exists():
            raise HTTPException(400, "没有地图草稿。")
        dest = game_stage_png(stage_id)
        _write_commit(src, dest, keyed=False)
        bible = _read_json(_stage_dir(stage_id) / "bible.json")
        upsert_stage(stage_id, bible, dest)
        src.unlink(missing_ok=True)
        bgm_packed = False
        bgm_src = draft_stage_bgm(stage_id)
        if bgm_src.exists():
            meta_path = bgm_src.with_suffix(".meta.json")
            meta: dict = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    meta = {}
            bgm_dest = game_stage_bgm(stage_id)
            bgm_dest.parent.mkdir(parents=True, exist_ok=True)
            if bgm_dest.exists():
                _archive_if_exists(bgm_dest)
            shutil.copy2(bgm_src, bgm_dest)
            bgm_src.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
            upsert_stage_bgm(stage_id, meta)
            bgm_packed = True
        refresh_index()
        payload = {
            "kind": "stage",
            "bible": bible,
            "asset": _asset_view(draft_stage_png(stage_id), dest),
            "stages": _list_stages(),
        }
        if bgm_packed:
            payload["bgm_asset"] = _stage_bgm_view(stage_id)
            payload["bgm_packed"] = True
        return payload

    _require_herogame()
    hero_id = _safe_id(body.hero_id)
    slot_id = body.slot_id
    if slot_id not in {s["id"] for s in HERO_SLOTS}:
        raise HTTPException(400, f"未知槽位 {slot_id}")
    src = draft_hero_png(hero_id, slot_id)
    if not src.exists():
        alt = source_hero_png(hero_id, slot_id)
        src = alt if alt.exists() else src
    slot = SLOT_BY_ID[slot_id]
    dest = game_hero_png(hero_id, slot_id)
    apply_key = keyed and slot.get("kind") == "sprite"
    saved = load_split_layout(hero_id, slot_id)
    frames = _resolve_split_frames(slot_id, None, saved)
    packed: bytes | None = None
    if slot.get("kind") == "sprite" and frames > 1:
        view = _hero_asset_view(hero_id, slot_id)
        split_n = len(view.get("frames") or [])
        if split_n < 2 or view.get("frames_stale"):
            raise HTTPException(400, "请先「一键切分」并播放确认，再入库。切分只预览，不会写入游戏。")
        frames = split_n
        buf = BytesIO()
        assemble_split_sheet(hero_id, slot_id).save(buf, format="PNG")
        packed = buf.getvalue()
    elif not src.exists():
        raise HTTPException(400, "没有这张草稿。先点「再出一版草稿」。")
    _write_commit(src if src.exists() else dest, dest, keyed=apply_key, frames=frames, pack=False, raw=packed)
    if packed is not None:
        mark_split_applied(hero_id, slot_id)
    bible = _read_bible(hero_id)
    upsert_fighter(hero_id, bible, slot_id, dest, apply_key, frames=frames)
    select_file = _maybe_bake_select(hero_id, slot_id)
    _clear_score(hero_id, slot_id)
    refresh_index()
    payload = {
        "kind": "hero",
        "hero_id": hero_id,
        "slot_id": slot_id,
        "asset": _hero_asset_view(hero_id, slot_id),
        "game_file": str(dest.relative_to(paths.game)),
    }
    if select_file:
        payload["select_file"] = select_file
        payload["select_icon"] = _hero_select_icon_view(hero_id)
    return payload


@app.post("/api/discard")
def discard_asset(body: DiscardBody) -> dict:
    if body.kind == "style":
        draft_style_png().unlink(missing_ok=True)
        return {"kind": "style", "style": _style_payload()}
    if body.kind == "stage":
        stage_id = _safe_id(body.stage_id)
        draft_stage_png(stage_id).unlink(missing_ok=True)
        return {
            "kind": "stage",
            "asset": _asset_view(draft_stage_png(stage_id), committed_stage_png(stage_id)),
            "stages": _list_stages(),
        }
    hero_id = _safe_id(body.hero_id)
    slot_id = body.slot_id
    draft_hero_png(hero_id, slot_id).unlink(missing_ok=True)
    source_hero_png(hero_id, slot_id).unlink(missing_ok=True)
    _clear_score(hero_id, slot_id)
    clear_split_frames(hero_id, slot_id)
    view = _hero_asset_view(hero_id, slot_id)
    return {
        "kind": "hero",
        "hero_id": hero_id,
        "slot_id": slot_id,
        "asset": view,
    }


@app.post("/api/rekey")
def rekey_asset(body: CommitBody) -> dict:
    if body.kind != "hero":
        raise HTTPException(400, "只有英雄精灵需要重新去青。")
    hero_id = _safe_id(body.hero_id)
    slot_id = body.slot_id
    if slot_id not in {s["id"] for s in HERO_SLOTS}:
        raise HTTPException(400, f"未知槽位 {slot_id}")
    slot = SLOT_BY_ID[slot_id]
    if slot.get("kind") != "sprite":
        raise HTTPException(400, "CG 不去青。")
    dest = game_hero_png(hero_id, slot_id)
    if not dest.exists():
        raise HTTPException(400, "这一张还没入库。请先切分确认后再点「采用入库」。")
    saved = load_split_layout(hero_id, slot_id)
    frames = _resolve_split_frames(slot_id, None, saved)
    try:
        fighter = json.loads(fighter_path(hero_id).read_text(encoding="utf-8")) if fighter_path(hero_id).exists() else {}
        existing = ((fighter.get("sprites") or {}).get(slot_id) or {}).get("frames")
        if existing in (5, 6) or (isinstance(existing, int) and existing >= 2):
            frames = int(existing)
    except Exception:  # noqa: BLE001
        pass
    _write_commit(dest, dest, keyed=True, frames=frames, pack=False, strict=True)
    bible = _read_bible(hero_id)
    upsert_fighter(hero_id, bible, slot_id, dest, True, frames=frames)
    select_file = _maybe_bake_select(hero_id, slot_id)
    refresh_index()
    view = _hero_asset_view(hero_id, slot_id)
    payload = {
        "kind": "hero",
        "hero_id": hero_id,
        "slot_id": slot_id,
        "asset": view,
        "game_file": str(dest.relative_to(paths.game)),
    }
    if select_file:
        payload["select_file"] = select_file
        payload["select_icon"] = _hero_select_icon_view(hero_id)
    return payload


@app.post("/api/uncommit")
def uncommit_asset(body: DiscardBody) -> dict:
    if body.kind == "style":
        raise HTTPException(400, "风格锚点入库后不可更改、不可撤回。")
    if body.kind == "stage":
        stage_id = _safe_id(body.stage_id)
        src = game_stage_png(stage_id)
        if not src.exists():
            raise HTTPException(400, "这张地图还没入库。")
        draft = draft_stage_png(stage_id)
        draft.parent.mkdir(parents=True, exist_ok=True)
        if not draft.exists():
            shutil.copy2(src, draft)
        src.unlink(missing_ok=True)
        refresh_index()
        return {
            "kind": "stage",
            "asset": _asset_view(draft, committed_stage_png(stage_id)),
            "stages": _list_stages(),
        }
    hero_id = _safe_id(body.hero_id)
    slot_id = body.slot_id
    if slot_id not in {s["id"] for s in HERO_SLOTS}:
        raise HTTPException(400, f"未知槽位 {slot_id}")
    src = game_hero_png(hero_id, slot_id)
    if not src.exists():
        raise HTTPException(400, "这一张还没入库。")
    draft = draft_hero_png(hero_id, slot_id)
    draft.parent.mkdir(parents=True, exist_ok=True)
    if not draft.exists():
        shutil.copy2(src, draft)
    _archive_if_exists(src)
    src.unlink(missing_ok=True)
    remove_fighter_slot(hero_id, slot_id)
    return {
        "kind": "hero",
        "hero_id": hero_id,
        "slot_id": slot_id,
        "asset": _hero_asset_view(hero_id, slot_id),
    }


@app.post("/api/split")
def split_hero_slot(body: SplitBody) -> dict:
    hero_id = _safe_id(body.hero_id)
    slot_id = body.slot_id
    if slot_id not in {s["id"] for s in HERO_SLOTS}:
        raise HTTPException(400, f"未知槽位 {slot_id}")
    frames = _resolve_split_frames(slot_id, body.frames)
    if frames < 2:
        raise HTTPException(400, "这一张不是分镜条，不用切。")
    src = ensure_split_source(hero_id, slot_id)
    if not src:
        raise HTTPException(400, "还没有图可切。先生成套图。")
    variant = body.variant
    if variant is None:
        variant = next_split_variant(hero_id, slot_id)
    variant = int(variant) % max(1, SPLIT_VARIANT_COUNT)
    # Real 2×2 contact sheets must unpack as a grid. Single-row 4-frame
    # turnarounds are not 2×2 — skip that method or 重新切分 loops on an error.
    grid = False
    if frames == 4:
        try:
            grid = bool(looks_like_grid_2x2(Image.open(src)))
        except Exception:  # noqa: BLE001
            grid = False
    if grid:
        variant = 5
    elif variant == 5:
        variant = 0
    try:
        split_strip(src, draft_hero_frames_dir(hero_id, slot_id), frames, variant=variant)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    # 记住开发者选的帧数，覆盖入库时 fighter.json 跟它走
    meta_path = draft_hero_frames_dir(hero_id, slot_id) / "cells.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(meta, dict):
                meta["split_frames"] = frames
                meta["expected"] = frames
                meta_path.write_text(json.dumps(meta), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    view = _hero_asset_view(hero_id, slot_id)
    return {
        "hero_id": hero_id,
        "slot_id": slot_id,
        "asset": view,
        "frames": view.get("frames") or [],
        "frame_count": frames,
        "variant": view.get("split_variant"),
        "variant_label": view.get("split_label"),
    }


def _slot_title_map() -> dict[str, str]:
    return {s["id"]: s.get("title") or s["id"] for s in HERO_SLOTS}


def _chart_payload(chart: dict) -> dict:
    path = Path(chart["path"])
    return {
        **chart,
        "chart_url": _file_url(path) if path.exists() else "",
    }


@app.get("/api/heroes/{hero_id}/select-crop-source")
def hero_select_crop_source(hero_id: str, source_slot: str = "") -> dict:
    """选人裁剪源：第 0 帧整格 + 自动建议框（像素坐标）。"""
    _require_herogame()
    hid = _safe_id(hero_id)
    slot_pref = (source_slot or "").strip() or None
    loaded = select_source_cell(hid, source_slot=slot_pref)
    if not loaded:
        raise HTTPException(400, "没有已入库的三视图或 idle，无法裁剪选人头像。")
    src_slot, cell, (sx, sy, ss) = loaded
    available: list[str] = []
    for slot in ("turnaround", "idle"):
        path = committed_hero_png(hid, slot)
        if path and path.exists():
            available.append(slot)
    # Persist a lightweight preview under drafts so the crop UI can load it as an image URL.
    preview_dir = paths.drafts / "heroes" / hid
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview = preview_dir / f"select_crop_src_{src_slot}.png"
    cell.save(preview, format="PNG")
    # Reuse last manual crop from fighter.json when same source.
    saved_crop = None
    fp = fighter_path(hid)
    if fp.exists():
        try:
            fighter = json.loads(fp.read_text(encoding="utf-8"))
            sel = (fighter.get("sprites") or {}).get("select") or {}
            raw = sel.get("crop") if isinstance(sel, dict) else None
            if isinstance(raw, dict) and sel.get("source") == src_slot:
                saved_crop = {
                    "x": int(raw.get("x") or sx),
                    "y": int(raw.get("y") or sy),
                    "size": int(raw.get("size") or ss),
                    "manual": bool(raw.get("manual")),
                }
        except Exception:  # noqa: BLE001
            saved_crop = None
    return {
        "ok": True,
        "hero_id": hid,
        "source_slot": src_slot,
        "available_slots": available,
        "cell_width": cell.size[0],
        "cell_height": cell.size[1],
        "suggest": {"x": sx, "y": sy, "size": ss},
        "saved_crop": saved_crop,
        "frame_url": _file_url(preview),
    }


@app.post("/api/heroes/bake-select")
def bake_hero_select_api(body: HeroBakeSelectBody) -> dict:
    """从 turnaround/idle 烘焙选人卡头像 select.png（128×128）。可选手动裁剪框。"""
    _require_herogame()
    if body.hero_id.strip():
        hero_id = _safe_id(body.hero_id)
        crop = None
        if body.crop_size is not None and body.crop_x is not None and body.crop_y is not None:
            crop = (int(body.crop_x), int(body.crop_y), int(body.crop_size))
        dest = bake_hero_select_portrait(
            hero_id,
            source_slot=(body.source_slot or "").strip() or None,
            crop=crop,
        )
        if not dest:
            raise HTTPException(400, "没有已入库的三视图或 idle，无法烘焙 select.png。")
        return {
            "ok": True,
            "hero_id": hero_id,
            "select_file": str(dest.relative_to(paths.game)),
            "select_icon": _hero_select_icon_view(hero_id),
        }
    results = bake_all_hero_select_portraits()
    ok_n = sum(1 for row in results if row.get("ok"))
    return {"ok": True, "baked": ok_n, "total": len(results), "results": results}


@app.post("/api/heroes/unify-body-scale")
def unify_hero_body_scale_api(body: UnifyBodyScaleBody) -> dict:
    """以 idle（或指定槽）人物墨迹高度为基准，一键对齐已入库各动作条体积。不重新生图。"""
    _require_style_locked()
    hero_id = _safe_id(body.hero_id)
    ref = (body.ref_slot or "idle").strip() or "idle"
    if ref.startswith("fx_"):
        raise HTTPException(400, "不能用弹道特效作身长基准。")
    if ref not in {s["id"] for s in HERO_SLOTS}:
        raise HTTPException(400, f"未知基准槽位 {ref}")
    try:
        result = unify_hero_body_scale(hero_id, ref_slot=ref)
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    refresh_index()
    chart: dict = {}
    try:
        chart = _chart_payload(build_body_scale_chart(hero_id, ref_slot=ref, titles=_slot_title_map()))
    except Exception:  # noqa: BLE001
        chart = {}
    return {
        **result,
        "chart": chart,
        "chart_url": chart.get("chart_url") or "",
        "assets": {s["id"]: _hero_asset_view(hero_id, s["id"]) for s in HERO_SLOTS},
    }


@app.post("/api/heroes/body-scale-chart")
def body_scale_chart_api(body: BodyScaleChartBody) -> dict:
    """生成/刷新身长对照大图：各套图上下叠放 + 左侧刻度尺，用于核验统一尺寸是否成功。"""
    _require_style_locked()
    hero_id = _safe_id(body.hero_id)
    ref = (body.ref_slot or "idle").strip() or "idle"
    if ref.startswith("fx_"):
        raise HTTPException(400, "不能用弹道特效作身长基准。")
    if ref not in {s["id"] for s in HERO_SLOTS}:
        raise HTTPException(400, f"未知基准槽位 {ref}")
    try:
        chart = build_body_scale_chart(hero_id, ref_slot=ref, titles=_slot_title_map())
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _chart_payload(chart)


def _body_scale_slot_payload(hero_id: str, slot_id: str, ref: str, *, force: bool = False) -> dict:
    if force:
        ensure_committed_equal_frames(hero_id, slot_id, force=True)
    detail = describe_body_scale_slot(
        hero_id,
        slot_id,
        ref_slot=ref,
        titles=_slot_title_map(),
        ensure=True,
    )
    files = list_split_frames(hero_id, slot_id)
    frames = []
    for i, meta in enumerate(detail.get("frames") or []):
        item = dict(meta)
        if i < len(files):
            item["url"] = _file_url(files[i])
        frames.append(item)
    detail["frames"] = frames
    detail["asset"] = _hero_asset_view(hero_id, slot_id)
    return detail


@app.post("/api/heroes/body-guide")
def body_guide_api(body: BodyGuideBody) -> dict:
    """Set or clear this hero's workshop head↔feet guide span (library default = 560)."""
    _require_style_locked()
    hero_id = _safe_id(body.hero_id)
    try:
        result = set_hero_body_guide(
            hero_id,
            body.body_guide_h,
            sync_visual_scale=bool(body.sync_visual_scale),
        )
        workspace = list_body_scale_workspace(hero_id, ref_slot="idle", titles=_slot_title_map())
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    refresh_index()
    return {**result, "workspace": workspace}


@app.post("/api/heroes/body-scale-workspace")
def body_scale_workspace_api(body: BodyScaleWorkspaceBody) -> dict:
    """身长校对工作区：列出已入库套图相对 idle 躯干身高的齐/差。"""
    _require_style_locked()
    hero_id = _safe_id(body.hero_id)
    ref = (body.ref_slot or "idle").strip() or "idle"
    if ref.startswith("fx_"):
        raise HTTPException(400, "不能用弹道特效作身长基准。")
    if ref not in {s["id"] for s in HERO_SLOTS}:
        raise HTTPException(400, f"未知基准槽位 {ref}")
    try:
        data = list_body_scale_workspace(hero_id, ref_slot=ref, titles=_slot_title_map())
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return data


@app.post("/api/heroes/body-scale-slot")
def body_scale_slot_api(body: BodyScaleSlotBody) -> dict:
    """打开某一套图的切分帧，带躯干测高，供工作区逐帧对照刻度。"""
    _require_style_locked()
    hero_id = _safe_id(body.hero_id)
    slot_id = body.slot_id
    ref = (body.ref_slot or "idle").strip() or "idle"
    if slot_id not in {s["id"] for s in HERO_SLOTS} or slot_id.startswith("fx_"):
        raise HTTPException(400, f"未知或不可校对槽位 {slot_id}")
    if ref.startswith("fx_"):
        raise HTTPException(400, "不能用弹道特效作身长基准。")
    try:
        return _body_scale_slot_payload(hero_id, slot_id, ref, force=bool(body.force_resplit))
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/heroes/body-scale-save")
def body_scale_save_api(body: BodyScaleSaveBody) -> dict:
    """按帧缩放后组装入库，供游戏直接调用。"""
    _require_style_locked()
    hero_id = _safe_id(body.hero_id)
    slot_id = body.slot_id
    ref = (body.ref_slot or "idle").strip() or "idle"
    if slot_id not in {s["id"] for s in HERO_SLOTS} or slot_id.startswith("fx_"):
        raise HTTPException(400, f"未知或不可校对槽位 {slot_id}")
    scales: dict[int, float] = {}
    feet_dys: dict[int, int] = {}
    mirrors: dict[int, bool] = {}
    for item in body.frames or []:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index"))
            scale = float(item.get("scale", 1.0))
        except (TypeError, ValueError):
            continue
        scales[idx] = scale
        try:
            feet_dys[idx] = int(round(float(item.get("feet_dy", 0) or 0)))
        except (TypeError, ValueError):
            feet_dys[idx] = 0
        mirrors[idx] = bool(item.get("mirror"))
    order = None
    if body.order is not None:
        try:
            order = [int(x) for x in body.order]
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, f"帧顺序无效: {exc}") from exc
    try:
        result = save_body_scale_slot(
            hero_id,
            slot_id,
            scales,
            ref_slot=ref,
            feet_dys=feet_dys,
            mirrors=mirrors,
            order=order,
        )
        detail = _body_scale_slot_payload(hero_id, slot_id, ref, force=False)
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    refresh_index()
    return {
        **result,
        "slot": detail,
        "asset": detail.get("asset"),
        "assets": {s["id"]: _hero_asset_view(hero_id, s["id"]) for s in HERO_SLOTS},
    }


@app.post("/api/heroes/ref-photo")
async def upload_hero_ref_photo(
    file: UploadFile = File(...),
    hero_id: str = Form(""),
    appearance: str = Form(""),
) -> dict:
    """Upload a real-person likeness photo used when generating turnaround."""
    _require_style_locked()
    raw_id = (hero_id or "").strip()
    if raw_id:
        hid = _safe_id(raw_id)
    else:
        seed = (appearance or "").strip() or f"hero_{int(time.time())}"
        hid = _safe_id(seed)
    bible = _read_bible(hid)
    if not bible:
        brief = (appearance or "").strip()
        bible = {
            "hero_id": hid,
            "display_name": (brief or hid)[:24],
            "appearance": brief,
            "description": brief,
            "prompts": {},
        }
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "空文件。")
    try:
        im = Image.open(BytesIO(raw)).convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"无法读取图片：{exc}") from exc
    max_side = 1536
    w, h = im.size
    if max(w, h) > max_side:
        scale = max_side / float(max(w, h))
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    dest = _ref_photo_path(hid)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, format="PNG")
    bible["hero_id"] = hid
    bible["has_ref_photo"] = True
    if (appearance or "").strip() and not str(bible.get("appearance") or "").strip():
        bible["appearance"] = appearance.strip()
    prompts = bible.get("prompts") if isinstance(bible.get("prompts"), dict) else {}
    ta = str(prompts.get("turnaround") or "")
    if ta and "NO character photo is attached" in ta:
        prompts["turnaround"] = ta.replace(
            "NO character photo is attached. Invent this fighter from CHARACTER LOCK only.",
            "A likeness REFERENCE PHOTO is attached first. Match that person in pixel art.",
            1,
        )
        bible["prompts"] = prompts
    _write_bible(hid, bible)
    return _hero_payload(hid, bible)


@app.post("/api/heroes/ref-photo/clear")
def clear_hero_ref_photo(body: HeroRefClearBody) -> dict:
    hid = _safe_id(body.hero_id) if body.hero_id else ""
    if not hid:
        raise HTTPException(400, "没有 hero_id。")
    _ref_photo_path(hid).unlink(missing_ok=True)
    bible = _read_bible(hid)
    if bible:
        bible.pop("has_ref_photo", None)
        _write_bible(hid, bible)
        return _hero_payload(hid, bible)
    return {"ok": True, "hero_id": hid, "ref_photo": {"url": "", "exists": False}, "bible": None}


@app.post("/api/upload-ref")
async def upload_ref(
    hero_id: str = Form(...),
    slot_id: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    if slot_id not in SLOT_BY_ID and slot_id != "custom":
        raise HTTPException(400, "未知槽位")
    hero_id = _safe_id(hero_id)
    dest = draft_hero_png(hero_id, slot_id if slot_id != "custom" else f"custom_{int(time.time())}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    raw = await file.read()
    try:
        im = Image.open(BytesIO(raw)).convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"无法读取图片：{exc}") from exc
    im.save(dest, format="PNG")
    return {
        "hero_id": hero_id,
        "slot_id": dest.stem,
        "asset": _asset_view(dest, committed_hero_png(hero_id, dest.stem)),
        "draft": True,
    }


@app.get("/api/tts/voices")
def tts_voices() -> dict:
    available_voices, _probe, _synth = _tts()
    project = vertex_status().get("project") or ""
    from tts_client import GEMINI_MODELS, available_languages

    return {
        "voices": available_voices(project),
        "models": GEMINI_MODELS,
        "languages": available_languages(project),
    }


@app.post("/api/voice/save")
def save_voice(body: VoiceSaveBody) -> dict:
    hero_id = _safe_id(body.hero_id)
    bible = _read_bible(hero_id)
    if not bible:
        raise HTTPException(400, "还没有这个英雄。先写出套图提示词。")
    _apply_voice(bible, body.voice, body.has_transform)
    _write_bible(hero_id, bible)
    return {"bible": bible, "voice_assets": _voice_assets(hero_id)}


@app.post("/api/voice/infer")
def infer_voice(body: VoiceInferBody) -> dict:
    hero_id = _safe_id(body.hero_id) if body.hero_id else ""
    bible = _read_bible(hero_id) if hero_id else {}
    description = (
        body.description
        or _compose_brief(bible.get("appearance", ""), bible.get("gear", ""), bible.get("kit_brief", ""), bible.get("description", ""))
    ).strip()
    if not description:
        raise HTTPException(400, "先写人物形象，或打开一个已有英雄。")
    kit = bible.get("kit") or {}
    form = body.voice or {}
    voice_prev = bible.get("voice") or {}
    lang = str(form.get("tts_language") or voice_prev.get("tts_language") or "cmn-CN").strip() or "cmn-CN"
    age = str(form.get("voice_age") or voice_prev.get("voice_age") or "adult").strip() or "adult"
    gender = str(form.get("gender") or voice_prev.get("gender") or "").strip()
    from prompts import VOICE_AGES, VOICE_LANGUAGES

    lang_hint = VOICE_LANGUAGES.get(lang, lang)
    age_hint = VOICE_AGES.get(age, age)
    gender_line = f"性别倾向：{gender}\n" if gender else ""
    user = (
        f"人物形象：{bible.get('appearance') or description}\n"
        f"武器配饰：{bible.get('gear') or '（见形象）'}\n"
        f"技能机制：{bible.get('kit_brief') or '（见形象）'}\n"
        f"中文名：{bible.get('display_name') or '（待定）'}\n"
        f"定位：{bible.get('one_liner') or '（待定）'}\n"
        f"台词语言：{lang_hint}（代码 {lang}）\n"
        f"说话人年龄：{age_hint}\n"
        f"{gender_line}"
        f"技能：地面普攻 {kit.get('attack') or '（无）'}；空中普攻 {kit.get('air_attack') or '（无）'}；"
        f"上+普攻 {kit.get('attack_up') or '（无）'}；下+普攻 {kit.get('attack_down') or '（无）'}；"
        f"地面小技能 {kit.get('skill') or '（无）'}；上+技能 {kit.get('combo_up') or kit.get('combo') or '（无）'}；"
        f"下+技能 {kit.get('combo_down') or '（无）'}；奥义 {kit.get('super') or '（无）'}\n"
        "不要写变身台词。请写出台词。"
    )
    try:
        data = json.loads(infer_json(VOICE_INFER_SYSTEM, user, body.vertex.to_settings()))
    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"台词结果不是合法 JSON：{exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc

    if not hero_id:
        raise HTTPException(400, "先写出套图提示词，生成 hero_id 后再写台词。")
    data["tts_language"] = lang
    data["voice_age"] = age
    data["tts_voice"] = form.get("tts_voice") or voice_prev.get("tts_voice") or data.get("tts_voice") or ""
    data["speaking_rate"] = (
        float(form["speaking_rate"]) if form.get("speaking_rate") is not None else voice_prev.get("speaking_rate", 1.0)
    )
    data["pitch"] = float(form["pitch"]) if form.get("pitch") is not None else voice_prev.get("pitch", 0.0)
    data["tts_engine"] = form.get("tts_engine") or voice_prev.get("tts_engine") or data.get("tts_engine") or "gemini"
    data["tts_model"] = form.get("tts_model") or voice_prev.get("tts_model") or data.get("tts_model") or ""
    if gender:
        data["gender"] = gender
    _apply_voice(bible, data, body.has_transform or bool(kit.get("transform")))
    bible["description"] = bible.get("description") or description
    _write_bible(hero_id, bible)
    return {"bible": bible, "voice_assets": _voice_assets(hero_id)}


def _save_voice_into_bible(hero_id: str, voice: dict, has_transform: bool) -> dict:
    bible = _read_bible(hero_id)
    if not bible:
        raise HTTPException(400, "还没有这个英雄。先写出套图提示词。")
    prev = bible.get("voice") or {}
    _apply_voice(bible, voice or bible.get("voice"), has_transform)
    _preserve_clone(bible["voice"], prev)
    _preserve_clone(bible["voice"], voice or {})
    _write_bible(hero_id, bible)
    return bible


@app.post("/api/voice/clone")
async def clone_voice(
    hero_id: str = Form(...),
    language_code: str = Form("cmn-CN"),
    same_clip: str = Form("0"),
    reference: UploadFile | None = File(None),
    consent: UploadFile | None = File(None),
) -> dict:
    hero_id = _safe_id(hero_id)
    bible = _read_bible(hero_id)
    if not bible:
        raise HTTPException(400, "还没有这个英雄。先写出套图提示词或保存进度。")
    if reference is None:
        raise HTTPException(400, "请上传或录制一段音色样本。")
    ref_bytes = await reference.read()
    consent_bytes = await consent.read() if consent is not None else b""
    if (same_clip in {"1", "true", "yes"} or not consent_bytes) and ref_bytes:
        consent_bytes = consent_bytes or ref_bytes
    if not consent_bytes:
        raise HTTPException(400, "请再传一段授权口播（须朗读授权文案），或勾选「用同一段录音」。")
    try:
        from tts_client import audio_encoding_for, generate_clone_key
    except ImportError as exc:
        raise HTTPException(500, "未安装 Cloud TTS 库。请安装 studio/requirements.txt") from exc
    ref_enc = audio_encoding_for(reference.filename or "", reference.content_type or "")
    consent_enc = audio_encoding_for(
        (consent.filename if consent is not None else reference.filename) or "",
        (consent.content_type if consent is not None else reference.content_type) or "",
    )
    project = vertex_status().get("project") or ""
    try:
        key = generate_clone_key(
            ref_bytes,
            consent_bytes,
            language_code=language_code or "cmn-CN",
            reference_encoding=ref_enc,
            consent_encoding=consent_enc,
            project=project,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc
    ref_path = draft_clone_audio(hero_id, "ref")
    consent_path = draft_clone_audio(hero_id, "consent")
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_bytes(ref_bytes)
    consent_path.write_bytes(consent_bytes)
    voice = bible.get("voice") or {}
    voice["clone_key"] = key
    voice["clone_language"] = language_code or "cmn-CN"
    voice["clone_ready"] = True
    voice["tts_engine"] = "clone"
    _apply_voice(bible, voice, _has_transform(bible))
    bible["voice"]["clone_key"] = key
    bible["voice"]["clone_language"] = language_code or "cmn-CN"
    bible["voice"]["clone_ready"] = True
    bible["voice"]["tts_engine"] = "clone"
    _write_bible(hero_id, bible)
    return _hero_payload(hero_id, bible)


@app.post("/api/voice/clone/clear")
def clear_clone_voice(body: HeroSaveBody) -> dict:
    hero_id = _safe_id(body.hero_id)
    bible = _read_bible(hero_id)
    if not bible:
        raise HTTPException(400, "还没有这个英雄。")
    voice = bible.get("voice") or {}
    voice["clone_key"] = ""
    voice["clone_ready"] = False
    if voice.get("tts_engine") == "clone":
        voice["tts_engine"] = "gemini"
    _apply_voice(bible, voice, _has_transform(bible))
    bible["voice"]["clone_key"] = ""
    bible["voice"]["clone_ready"] = False
    _write_bible(hero_id, bible)
    return _hero_payload(hero_id, bible)


@app.post("/api/tts/speak")
def tts_speak(body: TtsSpeakBody) -> dict:
    if body.line_id not in {s["id"] for s in VOICE_LINES}:
        raise HTTPException(400, f"未知台词槽 {body.line_id}")
    hero_id = _safe_id(body.hero_id)
    bible = _save_voice_into_bible(hero_id, body.voice, body.has_transform) if body.voice else _read_bible(hero_id)
    if not bible:
        raise HTTPException(400, "还没有这个英雄。")
    voice = bible.get("voice") or {}
    item = parse_line((voice.get("lines") or {}).get(body.line_id))
    text = (body.text or item.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "这句台词是空的。")
    tts_voice = body.tts_voice or voice.get("tts_voice") or "Charon"
    settings = vertex_status()
    project = settings.get("project") or ""
    _voices, _probe, synthesize = _tts()
    try:
        audio = synthesize(
            text,
            voice_name=tts_voice,
            speaking_rate=body.speaking_rate if body.speaking_rate else voice.get("speaking_rate") or 1.0,
            pitch=body.pitch if body.pitch is not None else (voice.get("pitch") or 0.0),
            project=project,
            engine=voice.get("tts_engine") or "",
            model_name=voice.get("tts_model") or "",
            emotion=item.get("emotion") or "",
            tag=item.get("tag") or "",
            line_id=body.line_id,
            persona=voice.get("persona") or "",
            display_name=bible.get("display_name") or "",
            gender=voice.get("gender") or "",
            clone_key=voice.get("clone_key") or "",
            clone_language=voice.get("clone_language") or "cmn-CN",
            tts_language=voice.get("tts_language") or "cmn-CN",
            voice_age=voice.get("voice_age") or "adult",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc
    dest = draft_voice_mp3(hero_id, body.line_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(audio)
    return {
        "bible": bible,
        "line_id": body.line_id,
        "url": _file_url(dest),
        "voice_assets": _voice_assets(hero_id),
    }


@app.post("/api/voice/commit")
def commit_voice(body: VoiceCommitBody) -> dict:
    hero_id = _safe_id(body.hero_id)
    bible = _save_voice_into_bible(hero_id, body.voice, body.has_transform)
    voice = bible.get("voice") or {}
    lines = voice.get("lines") or {}
    nonempty = []
    for slot in VOICE_LINES:
        item = parse_line(lines.get(slot["id"]))
        if item.get("text"):
            nonempty.append((slot["id"], item))
    if not nonempty:
        raise HTTPException(400, "没有可入库的台词。")
    settings = vertex_status()
    project = settings.get("project") or ""
    tts_voice = voice.get("tts_voice") or "Charon"
    _voices, _probe, synthesize = _tts()
    clips: dict[str, str] = {}
    for line_id, item in nonempty:
        dest_draft = draft_voice_mp3(hero_id, line_id)
        try:
            audio = synthesize(
                item["text"],
                voice_name=tts_voice,
                speaking_rate=float(voice.get("speaking_rate") or 1.0),
                pitch=float(voice.get("pitch") or 0.0),
                project=project,
                engine=voice.get("tts_engine") or "",
                model_name=voice.get("tts_model") or "",
                emotion=item.get("emotion") or "",
                tag=item.get("tag") or "",
                line_id=line_id,
                persona=voice.get("persona") or "",
                display_name=bible.get("display_name") or "",
                gender=voice.get("gender") or "",
                clone_key=voice.get("clone_key") or "",
                clone_language=voice.get("clone_language") or "cmn-CN",
                tts_language=voice.get("tts_language") or "cmn-CN",
                voice_age=voice.get("voice_age") or "adult",
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"{line_id} 合成失败：{exc}") from exc
        dest_draft.parent.mkdir(parents=True, exist_ok=True)
        dest_draft.write_bytes(audio)
        dest = game_voice_mp3(hero_id, line_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest_draft, dest)
        dest_draft.unlink(missing_ok=True)
        clips[line_id] = f"voice/{line_id}.mp3"
    fighter = upsert_fighter_voice(hero_id, bible, clips)
    return {
        "bible": bible,
        "voice_assets": _voice_assets(hero_id),
        "fighter": fighter,
        "clips": clips,
        "game_dir": f"heroes/{hero_id}/voice/",
    }


# ---------------------------------------------------------------------------
# 立绘 / 桌宠分区（不进 game/heroes，不去 fighter）
# ---------------------------------------------------------------------------


def _portrait_slots_from_specs(specs: list | None, *, fallback_all: bool = False) -> list[dict]:
    raw = []
    for s in specs or []:
        if hasattr(s, "model_dump"):
            raw.append(s.model_dump())
        elif isinstance(s, dict):
            raw.append(s)
        else:
            raw.append({"id": str(s)})
    return normalize_portrait_slot_list(raw, fallback_all=fallback_all)


def _portrait_payload(portrait_id: str, bible: dict | None = None) -> dict:
    data = dict(bible or read_portrait_bible(portrait_id) or {})
    data["portrait_id"] = portrait_id
    slots = resolve_portrait_slots(data, fallback_all=True)
    data["slots"] = slots
    data["slot_presets"] = PORTRAIT_SLOTS
    data["assets"] = {s["id"]: portrait_asset_view(portrait_id, s["id"], data) for s in slots}
    return data


@app.get("/api/portraits")
def list_portraits() -> dict:
    _require_deskpet()
    ensure_portrait_dirs()
    items = []
    for pid in list_portrait_ids():
        bible = read_portrait_bible(pid)
        items.append(
            {
                "portrait_id": pid,
                "display_name": bible.get("display_name") or pid,
                "one_liner": bible.get("one_liner") or "",
                "appearance": bible.get("appearance") or "",
                "slot_count": len(resolve_portrait_slots(bible, fallback_all=True)),
            }
        )
    return {
        "portraits": items,
        "slots": [
            normalize_portrait_slot(s)
            for s in PORTRAIT_SLOTS
            if s["id"] in PORTRAIT_DEFAULT_PLAN_IDS
        ],
        "slot_presets": PORTRAIT_SLOTS,
        "default_plan_ids": list(PORTRAIT_DEFAULT_PLAN_IDS),
    }


@app.get("/api/portraits/{portrait_id}")
def get_portrait(portrait_id: str) -> dict:
    _require_deskpet()
    pid = _safe_id(portrait_id)
    bible = read_portrait_bible(pid)
    if not bible:
        raise HTTPException(404, "没有这个立绘角色。")
    return _portrait_payload(pid, bible)


@app.post("/api/portraits")
def create_or_open_portrait(body: PortraitCreateBody) -> dict:
    _require_deskpet()
    _require_style_locked()
    appearance = (body.appearance or "").strip()
    gear = (body.gear or "").strip()
    if body.portrait_id:
        pid = _safe_id(body.portrait_id)
        bible = read_portrait_bible(pid) or {"portrait_id": pid, "prompts": {}}
    else:
        if len(appearance) < 2:
            raise HTTPException(400, "先写人物形象，或打开已有立绘。")
        pid = _safe_id(body.display_name or appearance)
        bible = read_portrait_bible(pid) or {"portrait_id": pid, "prompts": {}}
    if appearance:
        bible["appearance"] = appearance
    if gear:
        bible["gear"] = gear
    if body.display_name.strip():
        bible["display_name"] = body.display_name.strip()
    elif not bible.get("display_name"):
        bible["display_name"] = appearance[:24] or pid
    if body.slots:
        bible["slots"] = _portrait_slots_from_specs(body.slots, fallback_all=False)
    elif not bible.get("slots"):
        bible["slots"] = _portrait_slots_from_specs(
            [{"id": sid} for sid in PORTRAIT_DEFAULT_PLAN_IDS],
            fallback_all=False,
        )
    bible["portrait_id"] = pid
    bible.setdefault("prompts", {})
    write_portrait_bible(pid, bible)
    return _portrait_payload(pid, bible)


@app.post("/api/portraits/save")
def save_portrait(body: PortraitSaveBody) -> dict:
    """Persist appearance / gear / manually edited slot prompts (deskpet)."""
    _require_deskpet()
    pid = _safe_id(body.portrait_id)
    bible = read_portrait_bible(pid)
    if not bible:
        raise HTTPException(404, "没有这个立绘角色。")
    if body.appearance.strip():
        bible["appearance"] = body.appearance.strip()
    if body.gear.strip() or "gear" in bible:
        bible["gear"] = body.gear.strip()
    if body.display_name.strip():
        bible["display_name"] = body.display_name.strip()
    if body.prompts:
        prompts = dict(bible.get("prompts") or {})
        changed: list[str] = []
        plan_ids = {s["id"] for s in resolve_portrait_slots(bible, fallback_all=True)} | set(PORTRAIT_SLOT_IDS)
        for sid, text in body.prompts.items():
            if sid not in plan_ids:
                continue
            new = str(text or "")
            if new != str(prompts.get(sid) or ""):
                changed.append(sid)
            prompts[sid] = new
        bible["prompts"] = prompts
        if changed:
            times = bible.setdefault("prompt_times", {})
            now = time.time()
            for sid in changed:
                times[sid] = now
    write_portrait_bible(pid, bible)
    return _portrait_payload(pid, bible)


@app.post("/api/reveal-path")
def reveal_path(body: RevealPathBody) -> dict:
    """Open a project-local folder in the OS file manager (Finder / Explorer)."""
    target = (body.path or "").strip()
    if not target and body.portrait_id:
        _require_deskpet()
        pid = _safe_id(body.portrait_id)
        folder = export_portrait_dir(pid, body.slot_id.strip() or None)
        if not folder.exists() and body.slot_id:
            folder = export_portrait_dir(pid)
        target = str(folder)
    if not target:
        raise HTTPException(400, "缺少要打开的路径。")
    try:
        return reveal_in_file_manager(target)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc


@app.post("/api/portraits/infer")
def infer_portrait(body: PortraitInferBody) -> dict:
    _require_deskpet()
    _require_style_locked()
    appearance = (body.appearance or "").strip()
    gear = (body.gear or "").strip()
    pid = _safe_id(body.portrait_id) if body.portrait_id else ""
    existing = read_portrait_bible(pid) if pid else {}
    if not appearance:
        appearance = str(existing.get("appearance") or "")
    if not gear:
        gear = str(existing.get("gear") or "")
    if len(appearance) < 2:
        raise HTTPException(400, "请填写人物形象。")

    if body.slots:
        plan_slots = _portrait_slots_from_specs(body.slots, fallback_all=False)
    elif existing.get("slots"):
        plan_slots = resolve_portrait_slots(existing, fallback_all=False)
    else:
        plan_slots = _portrait_slots_from_specs(
            [{"id": sid} for sid in PORTRAIT_DEFAULT_PLAN_IDS],
            fallback_all=False,
        )
    if not plan_slots:
        raise HTTPException(400, "请至少选择一个套图类别。")
    motion = [s for s in plan_slots if s["id"] != "turnaround"]
    if motion and not any(s["id"] == "turnaround" for s in plan_slots):
        raise HTTPException(400, "有动作条时必须先包含「人物三视图」以锁定外形。")

    slot_lines = "\n".join(f"- {s['id']} / {s['title']} / {s['frames']} 帧" for s in plan_slots)
    user = (
        f"人物形象：{appearance}\n"
        f"人物配饰：{gear or '（未单列）'}\n"
        "这是桌宠/立绘小人，不是格斗角色。不要技能机制、不要战斗招式。\n"
        f"开发者已指定套图清单（只写这些，不要增删）：\n{slot_lines}"
    )
    try:
        raw = infer_json(portrait_infer_system_for(plan_slots), user, body.vertex.to_settings())
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"推理结果不是合法 JSON：{exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc

    if not pid:
        pid = _safe_id(str(data.get("portrait_id") or data.get("display_name") or appearance))
    bible = existing or {"portrait_id": pid, "prompts": {}}
    bible["portrait_id"] = pid
    bible["appearance"] = appearance
    if gear:
        bible["gear"] = gear
    if data.get("display_name"):
        bible["display_name"] = str(data["display_name"])
    elif not bible.get("display_name"):
        bible["display_name"] = appearance[:24]
    if data.get("one_liner"):
        bible["one_liner"] = str(data["one_liner"])
    if data.get("visual_lock"):
        bible["visual_lock"] = str(data["visual_lock"])
    else:
        bible["visual_lock"] = f"{appearance}" + (f"；{gear}" if gear else "")

    visual = bible.get("visual_lock") or ""
    name = str(bible.get("display_name") or "")
    raw_prompts = data.get("prompts") or data.get("slots") or {}
    wrapped: dict[str, str] = {}
    for slot in plan_slots:
        sid = slot["id"]
        normalize_portrait_slot(slot)
        body_txt = str(raw_prompts.get(sid) or "").strip()
        if not body_txt:
            body_txt = slot.get("hint") or sid
        wrapped[sid] = wrap_prompt(sid, body_txt, visual, display_name=name, product_line=KIND_DESKPET)
    bible["slots"] = plan_slots
    bible["prompts"] = wrapped
    times = bible.setdefault("prompt_times", {})
    now = time.time()
    for sid in wrapped:
        times[sid] = now
    write_portrait_bible(pid, bible)
    return _portrait_payload(pid, bible)


@app.post("/api/portraits/infer-slot")
def infer_portrait_slot(body: PortraitInferSlotBody) -> dict:
    """Rewrite one portrait slot prompt from a developer dissatisfaction note."""
    _require_deskpet()
    _require_style_locked()
    pid = _safe_id(body.portrait_id)
    bible = read_portrait_bible(pid)
    if not bible:
        raise HTTPException(400, "还没有这个立绘。先写出动作提示词。")
    plan_slots = resolve_portrait_slots(bible, fallback_all=True)
    slot = next((s for s in plan_slots if s["id"] == body.slot_id), None)
    if not slot:
        if body.slot_id in PORTRAIT_SLOT_IDS:
            slot = normalize_portrait_slot({"id": body.slot_id})
        else:
            raise HTTPException(400, f"未知立绘槽位 {body.slot_id}。")
    normalize_portrait_slot(slot)
    visual = bible.get("visual_lock") or ""
    prev = (bible.get("prompts") or {}).get(body.slot_id) or ""
    frames_n = int(slot.get("frames") or portrait_slot_frame_count(body.slot_id, bible))
    note = (body.note or "").strip()
    user = (
        f"人物形象：{bible.get('appearance') or ''}\n"
        f"人物配饰：{bible.get('gear') or '（未单列）'}\n"
        f"visual_lock：{visual}\n"
        f"要重写的槽：{body.slot_id}（{slot.get('title') or body.slot_id}）· exactly {frames_n} 帧\n"
        f"槽位要求：{slot.get('hint') or ''}\n"
        f"旧提示词：{prev or '（无）'}\n"
        f"开发者哪里不满意（必须写进新英文提示词并改掉，禁止复读旧稿）："
        f"{note or '（未写，请换一套分镜，不要复读旧稿）'}\n"
        "这是桌宠/立绘小人，不是格斗角色。只重写这一槽的英文生图提示词。"
    )
    try:
        raw = infer_json(PORTRAIT_SLOT_INFER_SYSTEM, user, body.vertex.to_settings())
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"推理结果不是合法 JSON：{exc}") from exc
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).strip() or exc.__class__.__name__
        raise HTTPException(502, f"微调提示词失败：{msg}") from exc
    if not isinstance(data, dict):
        raise HTTPException(502, "推理结果格式不对，请重试。")
    body_prompt = str(data.get("prompt") or "").strip()
    if not body_prompt and isinstance(data.get("prompts"), dict):
        body_prompt = str(data["prompts"].get(body.slot_id) or "").strip()
    if not body_prompt and isinstance(data.get("prompt"), dict):
        body_prompt = str(data["prompt"].get("en") or data["prompt"].get("text") or "").strip()
    if not body_prompt:
        raise HTTPException(502, "这一槽没有写出新提示词。请重试或换个说法描述不满意的点。")
    wrapped = wrap_prompt(
        body.slot_id,
        body_prompt,
        visual,
        developer_fix=note,
        display_name=str(bible.get("display_name") or ""),
        product_line=KIND_DESKPET,
    )
    if frames_n > 1:
        from prompts import enforce_strip_frame_count

        wrapped = enforce_strip_frame_count(wrapped, frames_n)
    prompts = bible.setdefault("prompts", {})
    prompts[body.slot_id] = wrapped
    zh = str(data.get("prompt_zh") or "").strip() or slot_zh_fallback(slot, note)
    if note and "已按意见" not in zh and note not in zh:
        zh = f"已按意见修改：{note}。{zh}"
    bible.setdefault("prompts_zh", {})[body.slot_id] = zh
    notes = bible.setdefault("prompt_notes", {})
    if note:
        notes[body.slot_id] = note
    else:
        notes.pop(body.slot_id, None)
    times = bible.setdefault("prompt_times", {})
    times[body.slot_id] = time.time()
    write_portrait_bible(pid, bible)
    payload = _portrait_payload(pid, bible)
    payload["slot_id"] = body.slot_id
    payload["prompt"] = wrapped
    payload["prompt_zh"] = zh
    return payload


@app.post("/api/portraits/generate")
def generate_portrait(body: PortraitGenerateBody) -> dict:
    _require_deskpet()
    _require_style_locked()
    pid = _safe_id(body.portrait_id)
    bible = read_portrait_bible(pid) or {"portrait_id": pid, "prompts": {}}
    plan_slots = resolve_portrait_slots(bible, fallback_all=True)
    slot = next((s for s in plan_slots if s["id"] == body.slot_id), None)
    if not slot:
        if body.slot_id in PORTRAIT_SLOT_IDS:
            slot = normalize_portrait_slot({"id": body.slot_id, "frames": body.frames})
        else:
            raise HTTPException(400, f"未知立绘槽位 {body.slot_id}。请先在套图清单里勾选。")
    if body.frames:
        slot = normalize_portrait_slot({**slot, "frames": body.frames})
    slot_meta = {**SLOT_BY_ID.get(body.slot_id, {}), **slot}
    normalize_portrait_slot(slot_meta)
    visual = body.visual_lock or bible.get("visual_lock") or ""
    prompt = (body.prompt or "").strip() or str((bible.get("prompts") or {}).get(body.slot_id) or "").strip()
    if not prompt:
        raise HTTPException(400, "提示词是空的。先点「写出提示词」。")
    expected = int(slot.get("frames") or portrait_slot_frame_count(body.slot_id, bible))
    if expected > 1:
        from prompts import enforce_strip_frame_count

        prompt = enforce_strip_frame_count(prompt, expected)

    needs_turnaround = body.slot_id != "turnaround" and any(s["id"] == "turnaround" for s in plan_slots)
    if needs_turnaround and not draft_portrait_png(pid, "turnaround").exists():
        raise HTTPException(400, "请先生成人物三视图，再画其他动作。")

    blobs: list[tuple[bytes, str]] = []
    labels: list[str] = []
    missing: list[str] = []
    used: list[str] = []

    def _push(path: Path | None, key: str, caption: str) -> None:
        before = len(blobs)
        _add_blob(blobs, missing, path, key)
        if len(blobs) > before:
            used.append(key)
            labels.append(caption)

    if body.slot_id != "turnaround":
        if draft_portrait_png(pid, "turnaround").exists():
            _push(
                draft_portrait_png(pid, "turnaround"),
                "turnaround",
                PORTRAIT_REF_LABEL_TURNAROUND,
            )
        _push(committed_style_png(), "style", PORTRAIT_REF_LABEL_STYLE)
    else:
        style_visual = (_style_payload().get("visual_lock") or "").strip()
        if style_visual and style_visual not in prompt:
            prompt = f"PIXEL LANGUAGE (text only): {style_visual}\n\n{prompt}"
        # Ensure turnaround drafts also carry chroma-safe lock even if prompt was hand-edited
        if PORTRAIT_CHROMA_SAFE not in prompt:
            prompt = f"{prompt}\n\n{PORTRAIT_CHROMA_SAFE}"

    dest = draft_portrait_png(pid, body.slot_id)
    settings = merge_settings(body.vertex.to_settings())
    strip = expected > 1
    max_tries = body.max_tries if body.max_tries > 0 else (2 if strip else 1)
    max_tries = max(1, min(int(max_tries), 3))

    if body.slot_id == "turnaround":
        layout_lock = (
            "\n\nHARD LAYOUT: ONE horizontal ROW, EXACTLY 4 FULL-BODY figures of THE SAME character. "
            "1 front, 2 three-quarter, 3 right-side, 4 back. Same costume and palette. "
            "DESK-PET / STANDING SPRITE turnaround — friendly readable silhouette, not a battle stance. "
            f"{PORTRAIT_CHROMA_SAFE} "
            f"FORBIDDEN: 2 rows, busts, three different people, cyan/teal clothing. {STRIP_SEPARATION}"
        )
    else:
        layout_lock = (
            f"\n\nHARD LAYOUT: ONE horizontal ROW, EXACTLY {expected} FULL-BODY figures. "
            "DESK-PET / STANDING SPRITE acting. No combat slash, no stage floor. "
            "IDENTITY: the FIRST attached image is the locked turnaround — copy THAT face, hair, "
            "ears, costume, props, and palette exactly; only the pose changes. "
            f"{PORTRAIT_CHROMA_SAFE} "
            f"{STRIP_SEPARATION}"
        )

    attempts = 0
    try:
        while True:
            attempts += 1
            use_prompt = prompt + layout_lock
            if attempts > 1:
                retry = TURNAROUND_RETRY if body.slot_id == "turnaround" else STRIP_RETRY.format(n=expected)
                use_prompt += f"\n\n{retry}"
            with _IMAGE_SEM:
                _save_draft(
                    dest=dest,
                    slot=slot_meta,
                    prompt=use_prompt,
                    blobs=blobs,
                    settings=settings,
                    reference_labels=labels,
                )
            if attempts >= max_tries or not strip:
                break
            layout = detect_strip_cells(Image.open(dest), expected)
            count_ok = layout.get("detected") == expected and layout.get("rows") == 1
            pipe = heuristic_score(dest.read_bytes(), slot_meta)
            div = diversity_score(pipe)
            need = 42 if body.slot_id == "idle" else 58
            if count_ok and (div is None or div >= need):
                break
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc

    plan_map = {s["id"]: dict(s) for s in plan_slots}
    plan_map[body.slot_id] = slot
    ordered = []
    seen = set()
    for s in plan_slots:
        ordered.append(plan_map.get(s["id"], s))
        seen.add(s["id"])
    if body.slot_id not in seen:
        ordered.append(slot)
    bible["slots"] = ordered
    bible["portrait_id"] = pid
    if body.display_name:
        bible["display_name"] = body.display_name
    if visual:
        bible["visual_lock"] = visual
    prompts = bible.get("prompts") or {}
    prompts[body.slot_id] = prompt
    bible["prompts"] = prompts
    write_portrait_bible(pid, bible)
    # New draft invalidates frozen source / split / cyan exports for this slot.
    reset_portrait_slot_derivatives(pid, body.slot_id)
    return {
        **_portrait_payload(pid, bible),
        "slot_id": body.slot_id,
        "asset": portrait_asset_view(pid, body.slot_id, bible),
        "missing_refs": missing,
        "used_refs": used,
        "attempts": attempts,
    }


@app.post("/api/portraits/split")
def split_portrait(body: PortraitSplitBody) -> dict:
    _require_deskpet()
    pid = _safe_id(body.portrait_id)
    bible = read_portrait_bible(pid) or {}
    plan_slots = resolve_portrait_slots(bible, fallback_all=True)
    if body.slot_id not in {s["id"] for s in plan_slots} and body.slot_id not in PORTRAIT_SLOT_IDS:
        raise HTTPException(400, f"未知立绘槽位 {body.slot_id}")
    n = body.frames
    if n is None:
        n = portrait_slot_frame_count(body.slot_id, bible)
    try:
        split_portrait_strip(
            pid,
            body.slot_id,
            frames=n,
            variant=int(body.variant or 0),
            bible=bible,
        )
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    view = portrait_asset_view(pid, body.slot_id, bible)
    return {
        "portrait_id": pid,
        "slot_id": body.slot_id,
        "asset": view,
        "frames": view.get("frames") or [],
        "frame_count": view.get("frame_count"),
    }


@app.post("/api/portraits/export")
def export_portrait(body: PortraitExportBody) -> dict:
    _require_deskpet()
    pid = _safe_id(body.portrait_id)
    bible = read_portrait_bible(pid) or {}
    plan_slots = resolve_portrait_slots(bible, fallback_all=True)
    slot_ids = [body.slot_id] if body.slot_id else [s["id"] for s in plan_slots]
    results = []
    errors = []
    allowed = {s["id"] for s in plan_slots} | set(PORTRAIT_SLOT_IDS)
    for sid in slot_ids:
        if sid not in allowed:
            continue
        try:
            results.append(export_portrait_slot(pid, sid, strict=bool(body.strict), bible=bible))
        except FileNotFoundError as exc:
            errors.append({"slot_id": sid, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            errors.append({"slot_id": sid, "error": str(exc)})
    if not results and errors:
        raise HTTPException(400, errors[0]["error"])
    return {
        "portrait_id": pid,
        "exports": results,
        "errors": errors,
        "payload": _portrait_payload(pid),
    }


@app.post("/api/portraits/discard")
def discard_portrait(body: PortraitDiscardBody) -> dict:
    _require_deskpet()
    pid = _safe_id(body.portrait_id)
    bible = read_portrait_bible(pid) or {}
    plan_slots = resolve_portrait_slots(bible, fallback_all=True)
    if body.slot_id not in {s["id"] for s in plan_slots} and body.slot_id not in PORTRAIT_SLOT_IDS:
        raise HTTPException(400, f"未知立绘槽位 {body.slot_id}")
    view = discard_portrait_slot(pid, body.slot_id)
    return {
        "portrait_id": pid,
        "slot_id": body.slot_id,
        "asset": view,
        "payload": _portrait_payload(pid),
    }


@app.post("/api/portraits/delete")
def delete_portrait_api(body: PortraitDeleteBody) -> dict:
    _require_deskpet()
    pid = _safe_id(body.portrait_id)
    if not pid:
        raise HTTPException(400, "没有 portrait_id。")
    if not read_portrait_bible(pid) and not (paths.drafts / "portraits" / pid).exists():
        # still allow cleaning orphan export/draft folders
        if not (paths.studio / "exports" / "portraits" / pid).exists() and not (
            paths.studio / "portraits" / pid
        ).exists():
            raise HTTPException(404, "没有这个立绘角色。")
    try:
        result = delete_portrait(pid)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    # Reuse list endpoint shape for the sidebar
    items = []
    for remaining in list_portrait_ids():
        bible = read_portrait_bible(remaining) or {}
        items.append(
            {
                "portrait_id": remaining,
                "display_name": bible.get("display_name") or remaining,
                "one_liner": bible.get("one_liner") or "",
                "appearance": bible.get("appearance") or "",
                "slot_count": len(resolve_portrait_slots(bible, fallback_all=True)),
            }
        )
    return {**result, "portraits": items}


@app.post("/api/portraits/body-scale-workspace")
def portrait_body_scale_workspace_api(body: PortraitBodyScaleWorkspaceBody) -> dict:
    _require_deskpet()
    _require_style_locked()
    pid = _safe_id(body.portrait_id)
    ref = (body.ref_slot or "idle").strip() or "idle"
    try:
        return list_portrait_body_scale_workspace(pid, ref_slot=ref)
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/portraits/body-scale-slot")
def portrait_body_scale_slot_api(body: PortraitBodyScaleSlotBody) -> dict:
    _require_deskpet()
    _require_style_locked()
    pid = _safe_id(body.portrait_id)
    ref = (body.ref_slot or "idle").strip() or "idle"
    try:
        return describe_portrait_body_scale_slot(
            pid,
            body.slot_id,
            ref_slot=ref,
            ensure=True,
            force=bool(body.force),
        )
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/portraits/body-scale-save")
def portrait_body_scale_save_api(body: PortraitBodyScaleSaveBody) -> dict:
    _require_deskpet()
    _require_style_locked()
    pid = _safe_id(body.portrait_id)
    ref = (body.ref_slot or "idle").strip() or "idle"
    scales: dict[int, float] = {}
    feet_dys: dict[int, int] = {}
    mirrors: dict[int, bool] = {}
    for item in body.frames or []:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index"))
            scale = float(item.get("scale", 1.0))
        except (TypeError, ValueError):
            continue
        scales[idx] = scale
        try:
            feet_dys[idx] = int(round(float(item.get("feet_dy", 0) or 0)))
        except (TypeError, ValueError):
            feet_dys[idx] = 0
        mirrors[idx] = bool(item.get("mirror"))
    order = None
    if body.order is not None:
        try:
            order = [int(x) for x in body.order]
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, f"帧顺序无效: {exc}") from exc
    try:
        result = save_portrait_body_scale_slot(
            pid,
            body.slot_id,
            scales,
            ref_slot=ref,
            feet_dys=feet_dys,
            mirrors=mirrors,
            order=order,
        )
        detail = describe_portrait_body_scale_slot(pid, body.slot_id, ref_slot=ref, ensure=False)
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        **result,
        "slot": detail,
        "asset": detail.get("asset"),
        "payload": _portrait_payload(pid),
    }


@app.post("/api/portraits/body-guide")
def portrait_body_guide_api(body: PortraitBodyGuideBody) -> dict:
    _require_deskpet()
    _require_style_locked()
    pid = _safe_id(body.portrait_id)
    try:
        guide = set_portrait_body_guide(pid, body.body_guide_h)
        workspace = list_portrait_body_scale_workspace(pid, ref_slot="idle")
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {**guide, "workspace": workspace, "payload": _portrait_payload(pid)}


@app.post("/api/portraits/unify-body-scale")
def portrait_unify_body_scale_api(body: PortraitUnifyBodyScaleBody) -> dict:
    _require_deskpet()
    _require_style_locked()
    pid = _safe_id(body.portrait_id)
    ref = (body.ref_slot or "idle").strip() or "idle"
    try:
        result = unify_portrait_body_scale(pid, ref_slot=ref)
        workspace = list_portrait_body_scale_workspace(pid, ref_slot=ref)
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        **result,
        "workspace": workspace,
        "payload": _portrait_payload(pid),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=8787, reload=True)
