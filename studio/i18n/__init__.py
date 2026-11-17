"""Server-side UI/API locale helpers for HeroGame Art Studio."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from fastapi import Request

ROOT = Path(__file__).resolve().parent
SUPPORTED = ("zh-CN", "en")
DEFAULT_LOCALE = "zh-CN"


def _catalog_dirs() -> list[Path]:
    dirs = [ROOT]
    # PyInstaller onedir may place --add-data JSON next to _MEIPASS/i18n.
    meipass = getattr(__import__("sys"), "_MEIPASS", None)
    if meipass:
        dirs.append(Path(meipass) / "i18n")
    # Web static locales remain a fallback for message catalogs.
    static_locales = ROOT.parent / "static" / "locales"
    if static_locales.is_dir():
        dirs.append(static_locales)
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in dirs:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(resolved)
    return ordered


def normalize_ui_locale(locale: str | None) -> str:
    raw = str(locale or "").strip().replace("_", "-")
    if not raw:
        return DEFAULT_LOCALE
    low = raw.lower()
    if low.startswith("en"):
        return "en"
    if low.startswith("zh"):
        return "zh-CN"
    return DEFAULT_LOCALE


@lru_cache(maxsize=8)
def _load_json(name: str) -> dict[str, str]:
    # Frontend locale filenames differ slightly from the API catalog names.
    aliases = {
        "messages_en.json": ("messages_en.json",),
        "messages_zh_CN.json": ("messages_zh_CN.json",),
        "runtime_en.json": ("runtime_en.json",),
        "api_en.json": ("api_en.json",),
    }
    names = aliases.get(name, (name,))
    for directory in _catalog_dirs():
        for candidate in names:
            path = directory / candidate
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                return {str(k): str(v) for k, v in data.items()}
    return {}


def messages(locale: str | None = None) -> dict[str, str]:
    loc = normalize_ui_locale(locale)
    if loc == "en":
        return _load_json("messages_en.json")
    return _load_json("messages_zh_CN.json")


def runtime_dict(locale: str | None = None) -> dict[str, str]:
    loc = normalize_ui_locale(locale)
    if loc == "en":
        return _load_json("runtime_en.json")
    return {}


def api_dict(locale: str | None = None) -> dict[str, str]:
    loc = normalize_ui_locale(locale)
    if loc == "en":
        return _load_json("api_en.json")
    return {}


def _format(template: str, params: dict | None = None) -> str:
    if not params:
        return template

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in params and params[key] is not None:
            return str(params[key])
        return match.group(0)

    return re.sub(r"\{(\w+)\}", repl, template)


def t(message: str, locale: str | None = None, **params: object) -> str:
    """Translate a Chinese source string (or dotted chrome key) for API/UI copy."""
    loc = normalize_ui_locale(locale)
    text = str(message or "")
    if not text:
        return text
    if "." in text and " " not in text and not re.search(r"[\u4e00-\u9fff]", text):
        catalog = messages(loc)
        text = catalog.get(text, text)
    elif loc == "en":
        text = runtime_dict("en").get(text) or api_dict("en").get(text) or text
    return _format(text, params or None)


def request_locale(request: Request | None = None, explicit: str | None = None) -> str:
    if explicit:
        return normalize_ui_locale(explicit)
    if request is None:
        return DEFAULT_LOCALE
    header = request.headers.get("x-studio-locale") or request.headers.get("accept-language") or ""
    if "," in header:
        header = header.split(",", 1)[0]
    if ";" in header:
        header = header.split(";", 1)[0]
    return normalize_ui_locale(header)


def http_detail(zh: str, request: Request | None = None, locale: str | None = None, **params: object) -> str:
    return t(zh, locale=request_locale(request, locale), **params)
