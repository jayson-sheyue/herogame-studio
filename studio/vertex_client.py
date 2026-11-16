"""Gemini clients for Vertex Express and Google AI Studio; API keys only."""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from google import genai
from google.genai import types

import api_credentials
from storage import write_json

log = logging.getLogger("studio.ai")
ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = ROOT / "settings.json"
DEFAULT_TEXT_MODEL = "gemini-3.8-flash"
DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image"
PROVIDERS = {"auto", "vertex", "ai_studio"}


def _normalize_settings_line(line: str | None) -> str:
    try:
        from project import VALID_KINDS, current_line, normalize_kind
        k = normalize_kind(line or current_line() or "")
        return k if k in VALID_KINDS else ""
    except Exception:
        return ""


def settings_path_for(line: str | None = None) -> Path:
    kind = _normalize_settings_line(line)
    return ROOT / f"settings.{kind}.json" if kind else SETTINGS_PATH


@dataclass(frozen=True)
class VertexSettings:
    # Keep the internal name to avoid changing every generation endpoint.
    provider: str = "auto"
    api_key: str = field(default="", repr=False)
    text_model: str = DEFAULT_TEXT_MODEL
    image_model: str = DEFAULT_IMAGE_MODEL
    key_storage: str = "missing"

    def cleaned(self) -> "VertexSettings":
        if not all(isinstance(value, str) for value in (self.provider, self.api_key, self.text_model, self.image_model)):
            raise ValueError("服务来源、密钥与模型名必须是文本。")
        provider = (self.provider or "auto").strip()
        if provider not in PROVIDERS:
            raise ValueError("请选择自动识别、Vertex AI Express 或 Google AI Studio。")
        key = (self.api_key or "").strip()
        if key and (len(key) > 4096 or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in key)):
            raise ValueError("API Key 格式无效，请粘贴完整密钥，不含空格或换行。")
        text_model = self.text_model.strip() or DEFAULT_TEXT_MODEL
        image_model = self.image_model.strip() or DEFAULT_IMAGE_MODEL
        for model in (text_model, image_model):
            if len(model) > 200 or not re.fullmatch(r"[a-zA-Z0-9._/-]+", model) or model.startswith(("AQ.", "AIza")) or model == key:
                raise ValueError("模型名无效。请填写模型标识，不要将密钥粘贴到模型字段。")
        return VertexSettings(provider, key, text_model, image_model, self.key_storage)

    @property
    def resolved_provider(self) -> str:
        if self.provider != "auto":
            return self.provider
        return "vertex" if self.api_key.startswith("AQ.") else "ai_studio"

    def public(self) -> dict:
        return {"provider": self.provider, "resolved_provider": self.resolved_provider,
                "text_model": self.text_model, "image_model": self.image_model,
                "api_key_set": bool(self.api_key), "key_storage": self.key_storage,
                "remember_api_key": self.key_storage == "system"}


def _saved_data(line=None) -> dict:
    path = settings_path_for(line)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        raise RuntimeError("无法读取本产品线设置，请检查设置文件的权限和 JSON 格式。") from None


def load_saved_settings(line: str | None = None) -> VertexSettings:
    with api_credentials.LOCK:
        data = _saved_data(line)
        key, source = api_credentials.read_key(api_credentials.slot_for(settings_path_for(line)), data.get("key_storage") == "system")
        return VertexSettings(
            provider=data.get("provider") or os.environ.get("STUDIO_API_PROVIDER") or "auto",
            api_key=key,
            text_model=data.get("text_model") or os.environ.get("STUDIO_TEXT_MODEL") or DEFAULT_TEXT_MODEL,
            image_model=data.get("image_model") or os.environ.get("STUDIO_IMAGE_MODEL") or DEFAULT_IMAGE_MODEL,
            key_storage=source,
        ).cleaned()


def merge_settings(incoming: VertexSettings | None, line: str | None = None) -> VertexSettings:
    # A resolved task snapshot must never read a replacement key during retries.
    if incoming is not None and incoming.api_key:
        return incoming.cleaned()
    saved = load_saved_settings(line)
    if incoming is None:
        return saved
    return VertexSettings(incoming.provider or saved.provider, saved.api_key,
                          incoming.text_model or saved.text_model,
                          incoming.image_model or saved.image_model, saved.key_storage).cleaned()


def save_settings(settings: VertexSettings, line: str | None = None, *, remember_api_key: bool | None = None, clear_api_key: bool = False) -> VertexSettings:
    with api_credentials.LOCK:
        data = _saved_data(line)
        # A new key can repair an inaccessible credential store without reading it.
        if settings.api_key or clear_api_key:
            cfg = VertexSettings(settings.provider or data.get("provider") or "auto", settings.api_key,
                                 settings.text_model or data.get("text_model") or DEFAULT_TEXT_MODEL,
                                 settings.image_model or data.get("image_model") or DEFAULT_IMAGE_MODEL).cleaned()
        else:
            cfg = merge_settings(settings, line)
        key = "" if clear_api_key else cfg.api_key
        persistent = (data.get("key_storage") == "system") if remember_api_key is None else remember_api_key
        persistent = persistent and bool(key)
        source = "system" if persistent else "session" if key else "missing"
        cfg = VertexSettings(cfg.provider, key, cfg.text_model, cfg.image_model, source)
        path = settings_path_for(line)
        public = {"provider": cfg.provider, "text_model": cfg.text_model, "image_model": cfg.image_model,
                  "key_storage": "system" if persistent else "session"}
        api_credentials.update_key(api_credentials.slot_for(path), key, persistent,
                                   data.get("key_storage") == "system", lambda: write_json(path, public))
        get_client.cache_clear()
        return cfg


def require_key(settings: VertexSettings) -> None:
    if not settings.api_key:
        raise ValueError("请在「API Key 设置」中输入密钥并保存。")


def redact(message: str, key: str = "") -> str:
    if key:
        message = message.replace(key, "[已隐藏密钥]")
    return re.sub(r"(?:AQ\.|AIza)[A-Za-z0-9_.~+/=\-]{8,}", "[已隐藏密钥]", message)


def _friendly_error(exc: BaseException, api_key: str = "") -> str:
    msg = redact(str(exc), api_key)
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    low = msg.lower()
    if code in (401, 403) or any(term in low for term in ("api key not valid", "permission_denied", "unauthenticated", "api_key_invalid")):
        return "API Key 无效、服务来源不匹配或权限不足。请检查密钥及其 API 限制，并手动选择正确的服务来源。"
    if code == 429 or "resource_exhausted" in low:
        return "请求受限或额度不足（429）。请检查此 Key 的配额与结算后再试。"
    if code == 404 or "not_found" in low:
        return "当前服务无法访问该模型（404）。请核对模型名及该服务的可用模型。"
    if any(term in low for term in ("timeout", "timed out", "connection", "ssl", "proxy")):
        return "连接 AI 服务失败或超时。请检查网络、代理及证书后重试。"
    return msg


def _call_with_backoff(fn, tries: int = 3, base: float = 1.25, *, api_key: str = ""):
    delay = base
    for attempt in range(tries):
        try:
            return fn()
        except Exception as exc:
            if not _transient(exc) or _rate_limited(exc) or attempt == tries - 1:
                raise RuntimeError(_friendly_error(exc, api_key)) from None
            # Log the class only; SDK exceptions may contain request credentials.
            log.warning("AI 服务瞬时失败（%s/%s）：%s", attempt + 1, tries, type(exc).__name__)
            time.sleep(delay + random.random() * 0.45)
            delay = min(delay * 2, 8)


@lru_cache(maxsize=8)
def get_client(provider: str, api_key: str) -> genai.Client:
    resolved = ("vertex" if api_key.startswith("AQ.") else "ai_studio") if provider == "auto" else provider
    if not api_key:
        raise ValueError("请先设置 API Key。")
    return genai.Client(vertexai=resolved == "vertex", api_key=api_key,
                        http_options=types.HttpOptions(timeout=120_000, api_version="v1" if resolved == "vertex" else "v1beta",
                            base_url="https://aiplatform.googleapis.com" if resolved == "vertex" else "https://generativelanguage.googleapis.com"))


def status() -> dict:
    try:
        cfg = load_saved_settings()
        return {**cfg.public(), "configured": bool(cfg.api_key),
                "error": None if cfg.api_key else "请先设置本产品线的 API Key。"}
    except Exception as exc:
        return {"configured": False, "api_key_set": False, "error": _friendly_error(exc)}


def infer_json(system: str, user: str, settings: VertexSettings | None = None) -> str:
    cfg = merge_settings(settings)
    require_key(cfg)
    response = _call_with_backoff(lambda: get_client(cfg.provider, cfg.api_key).models.generate_content(
        model=cfg.text_model, contents=user,
        config=types.GenerateContentConfig(system_instruction=system, temperature=0.8, response_mime_type="application/json")), api_key=cfg.api_key)
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("推理模型没有返回 JSON。")
    return text


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
            "connection refused",
            "network is unreachable",
            "unavailable",
            "502",
            "503",
            "504",
        )
    )


def generate_image(
    prompt: str,
    reference_blobs: list[tuple[bytes, str]],
    aspect_ratio: str = "16:9",
    image_size: str = "1K",
    settings: VertexSettings | None = None,
    reference_labels: list[str] | None = None,
) -> tuple[bytes, str]:
    cfg = merge_settings(settings)
    require_key(cfg)
    parts: list[types.Part] = []
    labels = reference_labels or []
    for i, (blob, mime) in enumerate(reference_blobs):
        label = labels[i].strip() if i < len(labels) and labels[i] else ""
        if label:
            parts.append(types.Part.from_text(text=f"REFERENCE IMAGE {i + 1}: {label}"))
        parts.append(types.Part.from_bytes(data=blob, mime_type=mime))
    parts.append(types.Part.from_text(text=prompt))

    def _run():
        client = get_client(cfg.provider, cfg.api_key)
        return client.models.generate_content(
            model=cfg.image_model,
            contents=parts,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                ),
            ),
        )

    response = _call_with_backoff(_run, api_key=cfg.api_key)
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
    checks = {}
    try:
        require_key(cfg)
        client = get_client(cfg.provider, cfg.api_key)
        for name, model in (("text_model", cfg.text_model), ("image_model", cfg.image_model)):
            try:
                client.models.count_tokens(model=model, contents="connection check")
                checks[name] = {"ok": True, "detail": f"{model} 的 countTokens 请求已响应；未执行内容生成。"}
            except Exception as exc:
                checks[name] = {"ok": False, "detail": _friendly_error(exc, cfg.api_key)}
    except Exception as exc:
        checks["api_key"] = {"ok": False, "detail": _friendly_error(exc, cfg.api_key)}
    return {"ok": bool(checks) and all(item["ok"] for item in checks.values()),
            "settings": cfg.public(), "checks": checks}
