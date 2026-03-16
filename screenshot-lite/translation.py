from __future__ import annotations

from deep_translator import GoogleTranslator

from screenshot-lite.settings_dialog import TranslationConfig


def translate_text(text: str, config: TranslationConfig) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    translator = GoogleTranslator(source=config.source_language, target=config.target_language)
    return translator.translate(cleaned)
