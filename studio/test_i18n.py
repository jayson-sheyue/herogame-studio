"""Offline checks for UI/API locale helpers."""

from __future__ import annotations

import unittest

from i18n import normalize_ui_locale, t
import i18n_prompts


class LocaleHelpersTest(unittest.TestCase):
    def test_normalize(self) -> None:
        self.assertEqual(normalize_ui_locale("en-US"), "en")
        self.assertEqual(normalize_ui_locale("zh"), "zh-CN")
        self.assertEqual(normalize_ui_locale(""), "zh-CN")

    def test_api_detail_english(self) -> None:
        zh = "请先选择产品线（对战游戏 / 桌宠立绘）。"
        en = t(zh, locale="en")
        self.assertNotEqual(en, zh)
        self.assertIn("product line", en.lower())

    def test_messages_key(self) -> None:
        self.assertEqual(t("ui.language", locale="zh-CN"), "界面语言")
        self.assertEqual(t("ui.language", locale="en"), "Interface language")

    def test_prompt_locale_switch(self) -> None:
        zh = i18n_prompts.style_infer_system("herogame", locale="zh-CN")
        en = i18n_prompts.style_infer_system("herogame", locale="en")
        self.assertIn("英灵大乱斗", zh)
        self.assertIn("Spirit Brawl", en)
        self.assertNotEqual(zh, en)


if __name__ == "__main__":
    unittest.main()
