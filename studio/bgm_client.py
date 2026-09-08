"""Lyria 3 Clip BGM generation via Vertex / Gemini Interactions API."""

from __future__ import annotations

import base64
import time
from pathlib import Path

from prompts import stage_bgm_prompt
from vertex_client import VertexSettings, _call_with_backoff, _require_project, get_client, merge_settings

LYRIA_CLIP_MODEL = "lyria-3-clip-preview"


def _decode_audio(data: object) -> bytes:
    if data is None:
        raise RuntimeError("Lyria 没有返回音频。")
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, str):
        return base64.b64decode(data)
    raw = getattr(data, "data", None)
    if raw is None:
        raise RuntimeError("Lyria 音频块为空。")
    return _decode_audio(raw)


def generate_stage_bgm(
    *,
    display_name: str,
    visual: str,
    bpm: int = 118,
    image_bytes: bytes | None = None,
    image_mime: str = "image/png",
    settings: VertexSettings | None = None,
) -> tuple[bytes, str, dict]:
    cfg = merge_settings(settings)
    project = _require_project(cfg)
    prompt = stage_bgm_prompt(display_name, visual, bpm=bpm)

    if image_bytes:
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        payload: object = [
            {"type": "text", "text": prompt},
            {"type": "image", "mime_type": image_mime or "image/png", "data": image_b64},
        ]
    else:
        payload = prompt

    def _run():
        client = get_client(project, cfg.location)
        return client.interactions.create(model=LYRIA_CLIP_MODEL, input=payload)

    interaction = _call_with_backoff(_run)
    output = interaction.output_audio
    if not output:
        note = (interaction.output_text or "").strip()
        raise RuntimeError("Lyria 没有返回 MP3。" + (f" 模型说：{note}" if note else ""))
    mp3 = _decode_audio(getattr(output, "data", output))
    if len(mp3) < 1024:
        raise RuntimeError("Lyria 返回的音频过短，可能生成失败。")
    note = (interaction.output_text or "").strip()
    meta = {
        "model": LYRIA_CLIP_MODEL,
        "bpm": bpm,
        "instrumental": True,
        "prompt": prompt,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if image_bytes:
        meta["imageRef"] = True
    return mp3, note, meta


def load_stage_reference_png(stage_id: str) -> tuple[bytes, str] | None:
    from game_assets import committed_stage_png, draft_stage_png

    for path in (draft_stage_png(stage_id), committed_stage_png(stage_id)):
        if path and path.exists():
            return path.read_bytes(), "image/png"
    return None
