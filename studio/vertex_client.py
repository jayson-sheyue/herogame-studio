"""Vertex AI Gemini client using Application Default Credentials."""

from __future__ import annotations

import json
import logging
import os
import random
import subprocess
import time
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

import google.auth
import requests
from google.auth.transport.requests import Request
from google.genai import types
from google import genai
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("studio.vertex")

ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = ROOT / "settings.json"

DEFAULT_LOCATION = "global"
DEFAULT_IMAGE_LOCATION = "global"
DEFAULT_TEXT_MODEL = "gemini-2.5-flash"
DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image"


def _normalize_settings_line(line: str | None) -> str:
    try:
        from project import VALID_KINDS, current_line, normalize_kind

        k = normalize_kind(line or current_line() or "")
        return k if k in VALID_KINDS else ""
    except Exception:
        return ""


def settings_path_for(line: str | None = None) -> Path:
    """Per-product-line Vertex settings. Legacy settings.json is only the unset-line fallback."""
    k = _normalize_settings_line(line)
    if k:
        return ROOT / f"settings.{k}.json"
    return SETTINGS_PATH


@dataclass
class VertexSettings:
    project: str = ""
    location: str = DEFAULT_LOCATION
    image_location: str = DEFAULT_IMAGE_LOCATION
    text_model: str = DEFAULT_TEXT_MODEL
    image_model: str = DEFAULT_IMAGE_MODEL

    def cleaned(self) -> "VertexSettings":
        location = (self.location or DEFAULT_LOCATION).strip() or DEFAULT_LOCATION
        image_location = (self.image_location or location).strip() or location
        return VertexSettings(
            project=(self.project or "").strip(),
            location=location,
            image_location=image_location,
            text_model=(self.text_model or DEFAULT_TEXT_MODEL).strip() or DEFAULT_TEXT_MODEL,
            image_model=(self.image_model or DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL,
        )


def _gcloud_project() -> str:
    env = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
    if env:
        return env.strip()
    try:
        out = subprocess.check_output(
            ["gcloud", "config", "get-value", "project"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def load_saved_settings(line: str | None = None) -> VertexSettings:
    """Load Vertex settings for the active product line.

    Product lines do not silently inherit each other's GCP project.
    Missing line file → empty project (models fall back to defaults / env).
    """
    path = settings_path_for(line)
    data: dict = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except json.JSONDecodeError:
            data = {}
    # Legacy global file only when no product line is selected
    if not data and path == SETTINGS_PATH and SETTINGS_PATH.exists():
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except json.JSONDecodeError:
            data = {}
    return VertexSettings(
        project=data.get("project") or (_gcloud_project() if not _normalize_settings_line(line) else ""),
        location=data.get("location") or os.environ.get("GOOGLE_CLOUD_LOCATION") or DEFAULT_LOCATION,
        image_location=(
            data.get("image_location")
            or os.environ.get("STUDIO_IMAGE_LOCATION")
            or data.get("location")
            or os.environ.get("GOOGLE_CLOUD_LOCATION")
            or DEFAULT_IMAGE_LOCATION
        ),
        text_model=data.get("text_model") or os.environ.get("STUDIO_TEXT_MODEL") or DEFAULT_TEXT_MODEL,
        image_model=data.get("image_model") or os.environ.get("STUDIO_IMAGE_MODEL") or DEFAULT_IMAGE_MODEL,
    ).cleaned()


def save_settings(settings: VertexSettings, line: str | None = None) -> VertexSettings:
    cleaned = settings.cleaned()
    path = settings_path_for(line)
    path.write_text(
        json.dumps(asdict(cleaned), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    # Keep legacy file in sync only when writing without a line (tool boot)
    if path != SETTINGS_PATH and not _normalize_settings_line(line):
        SETTINGS_PATH.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return cleaned


def merge_settings(incoming: VertexSettings | None, line: str | None = None) -> VertexSettings:
    if line is None:
        try:
            from project import current_line

            line = current_line() or None
        except Exception:  # noqa: BLE001
            line = None
    saved = load_saved_settings(line)
    if incoming is None:
        return saved
    raw = incoming.cleaned()
    return VertexSettings(
        project=raw.project or saved.project,
        location=raw.location or saved.location,
        image_location=raw.image_location or saved.image_location,
        text_model=raw.text_model or saved.text_model,
        image_model=raw.image_model or saved.image_model,
    ).cleaned()


def _require_project(settings: VertexSettings) -> str:
    if settings.project:
        return settings.project
    raise RuntimeError("请填写 GCP 项目 ID。")


def _rate_limited(exc: BaseException) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code == 429:
        return True
    status = str(getattr(exc, "status", "") or "").upper()
    if status in {"RESOURCE_EXHAUSTED", "429"}:
        return True
    msg = str(exc).lower()
    return (
        "429" in msg
        or "resource exhausted" in msg
        or "resource_exhausted" in msg
        or "too many requests" in msg
        or "rate-limit" in msg
        or "rate limit" in msg
    )


def _transient(exc: BaseException) -> bool:
    if _rate_limited(exc):
        return True
    name = type(exc).__name__.lower()
    if any(key in name for key in ("ssl", "timeout", "connection", "protocol", "proxy", "retry")):
        return True
    msg = str(exc).lower()
    return any(
        key in msg
        for key in (
            "ssl",
            "unexpected_eof",
            "eof occurred",
            "max retries exceeded",
            "connection reset",
            "connection aborted",
            "broken pipe",
            "temporarily unavailable",
            "timed out",
            "timeout",
            "oauth2.googleapis.com",
            "connection refused",
            "network is unreachable",
            "unavailable",
            "502",
            "503",
            "504",
        )
    )


def _friendly_error(exc: BaseException) -> str:
    msg = str(exc)
    low = msg.lower()
    if (
        "oauth2.googleapis.com" in low
        or "unexpected_eof" in low
        or ("ssl" in low and ("token" in low or "eof" in low))
    ):
        return (
            "刷新 Google 登录态失败：连 oauth2.googleapis.com 时 SSL 被中断。"
            "这通常是代理/VPN 瞬时断开，不是提示词写坏了。"
            "请确认系统代理可用后重试；仍不行就再跑一次 "
            "gcloud auth application-default login。"
            f" 原始错误：{msg}"
        )
    return msg


def _auth_request() -> Request:
    session = requests.Session()
    retry = Retry(
        total=6,
        connect=6,
        read=6,
        other=6,
        backoff_factor=0.7,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=None,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return Request(session=session)


def _adc_credentials():
    creds, detected = google.auth.default()
    if not getattr(creds, "valid", False):
        creds.refresh(_auth_request())
    return creds, detected


def _call_with_backoff(fn, tries: int = 6, base: float = 1.25):
    delay = base
    last: BaseException | None = None
    for attempt in range(tries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if not _transient(exc) or attempt == tries - 1:
                raise RuntimeError(_friendly_error(exc)) from exc
            get_client.cache_clear()
            wait = delay + random.random() * 0.45
            log.warning(
                "Vertex 瞬时失败（%s/%s），%.1fs 后重试：%s",
                attempt + 1,
                tries,
                wait,
                exc,
            )
            time.sleep(wait)
            delay = min(delay * 2, 32)
    raise RuntimeError(_friendly_error(last or RuntimeError("未知错误")))  # pragma: no cover


@lru_cache(maxsize=8)
def get_client(project: str, location: str) -> genai.Client:
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
    creds, _ = _adc_credentials()
    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
        credentials=creds,
    )


def status() -> dict:
    try:
        from project import current_line

        line = current_line() or None
    except Exception:  # noqa: BLE001
        line = None
    settings = load_saved_settings(line)
    adc = True
    error = None
    account = None
    try:
        creds, detected = _adc_credentials()
        account = getattr(creds, "service_account_email", None) or getattr(
            creds, "quota_project_id", None
        )
        if not settings.project and detected:
            settings.project = detected
        get_client(_require_project(settings), settings.location)
    except Exception as exc:  # noqa: BLE001
        adc = False
        error = _friendly_error(exc)
    payload = asdict(settings)
    payload.update({"adc": adc, "error": error, "account": account})
    return payload


def infer_json(system: str, user: str, settings: VertexSettings | None = None) -> str:
    cfg = merge_settings(settings)
    project = _require_project(cfg)

    def _run():
        client = get_client(project, cfg.location)
        return client.models.generate_content(
            model=cfg.text_model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.8,
                response_mime_type="application/json",
            ),
        )

    response = _call_with_backoff(_run)
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("推理模型没有返回 JSON。")
    return text


def generate_image(
    prompt: str,
    reference_blobs: list[tuple[bytes, str]],
    aspect_ratio: str = "16:9",
    image_size: str = "1K",
    settings: VertexSettings | None = None,
    reference_labels: list[str] | None = None,
) -> tuple[bytes, str]:
    cfg = merge_settings(settings)
    project = _require_project(cfg)
    parts: list[types.Part] = []
    labels = reference_labels or []
    for i, (blob, mime) in enumerate(reference_blobs):
        label = labels[i].strip() if i < len(labels) and labels[i] else ""
        if label:
            parts.append(types.Part.from_text(text=f"REFERENCE IMAGE {i + 1}: {label}"))
        parts.append(types.Part.from_bytes(data=blob, mime_type=mime))
    parts.append(types.Part.from_text(text=prompt))

    def _run():
        client = get_client(project, cfg.image_location)
        return client.models.generate_content(
            model=cfg.image_model,
            contents=parts,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                    person_generation="ALLOW_ALL",
                ),
            ),
        )

    response = _call_with_backoff(_run)
    note_bits: list[str] = []
    image_bytes: bytes | None = None
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise RuntimeError("图像模型没有返回候选（可能被安全策略拦截）。")
    for part in candidates[0].content.parts or []:
        if getattr(part, "text", None):
            note_bits.append(part.text.strip())
        inline = getattr(part, "inline_data", None)
        if inline and inline.data:
            image_bytes = inline.data
    if not image_bytes:
        raise RuntimeError(
            "图像模型没有返回图片。" + ((" 模型说：" + " ".join(note_bits)) if note_bits else "")
        )
    return image_bytes, " ".join(note_bits)


def probe(settings: VertexSettings) -> dict:
    cfg = settings.cleaned()
    checks: dict[str, dict] = {}

    try:
        creds, detected = _adc_credentials()
        account = getattr(creds, "service_account_email", None) or getattr(
            creds, "quota_project_id", None
        ) or detected
        checks["adc"] = {"ok": True, "detail": f"ADC 有效 · {account or 'user credentials'}"}
        if not cfg.project and detected:
            cfg.project = str(detected)
    except Exception as exc:  # noqa: BLE001
        checks["adc"] = {"ok": False, "detail": _friendly_error(exc)}
        return {"ok": False, "settings": asdict(cfg), "checks": checks}

    try:
        project = _require_project(cfg)
        text_client = get_client(project, cfg.location)
        checks["client"] = {
            "ok": True,
            "detail": f"提示词客户端 · {project} / {cfg.location}",
        }
    except Exception as exc:  # noqa: BLE001
        checks["client"] = {"ok": False, "detail": _friendly_error(exc)}
        return {"ok": False, "settings": asdict(cfg), "checks": checks}

    try:
        ping = text_client.models.generate_content(
            model=cfg.text_model,
            contents='Reply with the single word PONG and nothing else.',
            config=types.GenerateContentConfig(temperature=0),
        )
        text = (ping.text or "").strip().replace("\n", " ")
        checks["text_model"] = {
            "ok": True,
            "detail": f"{cfg.text_model} @ {cfg.location} 已响应：{text[:80] or '（空文本，但调用成功）'}",
        }
    except Exception as exc:  # noqa: BLE001
        checks["text_model"] = {"ok": False, "detail": _friendly_error(exc)}

    try:
        image_client = get_client(project, cfg.image_location)
        info = image_client.models.get(model=cfg.image_model)
        name = getattr(info, "name", None) or cfg.image_model
        checks["image_model"] = {
            "ok": True,
            "detail": f"{name} @ {cfg.image_location}",
        }
    except Exception as exc:  # noqa: BLE001
        checks["image_model"] = {
            "ok": False,
            "detail": f"{cfg.image_model} @ {cfg.image_location} 失败：{_friendly_error(exc)}",
        }

    ok = all(item.get("ok") for item in checks.values())
    if ok:
        save_settings(cfg)
        get_client.cache_clear()
    return {"ok": ok, "settings": asdict(cfg), "checks": checks}
