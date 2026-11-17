"""Locale-aware accessors for HeroStudio LLM system prompts."""

from __future__ import annotations

import prompts as prompts_zh
import prompts_en


def normalize_ui_locale(locale: str | None) -> str:
    return "en" if str(locale or "").lower().startswith("en") else "zh-CN"


def style_infer_system(product_line=None, locale="zh-CN"):
    if normalize_ui_locale(locale) == "en":
        return prompts_en.style_infer_system(product_line)
    return prompts_zh.style_infer_system(product_line)


def stage_infer_system(locale="zh-CN"):
    if normalize_ui_locale(locale) == "en":
        return prompts_en.STAGE_INFER_SYSTEM
    return prompts_zh.STAGE_INFER_SYSTEM


def hero_infer_system(locale="zh-CN"):
    if normalize_ui_locale(locale) == "en":
        return prompts_en.INFER_SYSTEM
    return prompts_zh.INFER_SYSTEM


def slot_infer_system(locale="zh-CN"):
    if normalize_ui_locale(locale) == "en":
        return prompts_en.SLOT_INFER_SYSTEM
    return prompts_zh.SLOT_INFER_SYSTEM


def portrait_infer_system_for(slots, locale="zh-CN"):
    if normalize_ui_locale(locale) == "en":
        return prompts_en.portrait_infer_system_for(slots)
    return prompts_zh.portrait_infer_system_for(slots)


def portrait_slot_infer_system(locale="zh-CN"):
    if normalize_ui_locale(locale) == "en":
        return prompts_en.PORTRAIT_SLOT_INFER_SYSTEM
    return prompts_zh.PORTRAIT_SLOT_INFER_SYSTEM


def voice_infer_system(locale="zh-CN"):
    if normalize_ui_locale(locale) == "en":
        return prompts_en.VOICE_INFER_SYSTEM
    return prompts_zh.VOICE_INFER_SYSTEM


def voice_lines(locale="zh-CN"):
    if normalize_ui_locale(locale) == "en":
        return prompts_en.VOICE_LINES_EN
    return prompts_zh.VOICE_LINES


def line_performance(locale="zh-CN"):
    if normalize_ui_locale(locale) == "en":
        return prompts_en.LINE_PERFORMANCE_EN
    return prompts_zh.LINE_PERFORMANCE
