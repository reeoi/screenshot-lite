from __future__ import annotations

import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QMessageBox, QPlainTextEdit, QVBoxLayout

from screenshot-lite.settings_dialog import TranslationConfig
from screenshot-lite.translation import translate_text


@lru_cache(maxsize=1)
def available_languages() -> set[str]:
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return set()
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return set(lines[1:]) if len(lines) > 1 else set(lines)


def recognize_text(pixmap: QPixmap) -> str:
    if pixmap.isNull():
        return ""

    with tempfile.TemporaryDirectory(prefix="screenshot_lite_ocr_") as tmpdir:
        image_path = Path(tmpdir) / "source.png"
        pixmap.save(str(image_path), "PNG")
        languages = available_languages()
        candidates = []
        if {"chi_sim", "eng"}.issubset(languages):
            candidates.append("chi_sim+eng")
        if "chi_sim" in languages:
            candidates.append("chi_sim")
        if "eng" in languages:
            candidates.append("eng")
        candidates.append("")

        variants = _build_ocr_variants(image_path, Path(tmpdir))
        best_text = ""
        best_score = -1.0
        for variant_path in variants:
            for language in candidates:
                for psm in (6, 11):
                    text = _run_tesseract(variant_path, language, psm)
                    score = _score_text(text)
                    if score > best_score:
                        best_score = score
                        best_text = text
        return best_text.strip()


def _build_ocr_variants(image_path: Path, temp_dir: Path) -> list[Path]:
    image = Image.open(image_path).convert("RGB")
    grayscale = ImageOps.autocontrast(image.convert("L"))

    variants: list[tuple[str, Image.Image]] = [("original", image)]

    upscaled = grayscale.resize(
        (max(1, grayscale.width * 2), max(1, grayscale.height * 2)),
        Image.Resampling.LANCZOS,
    )
    sharpened = ImageEnhance.Sharpness(upscaled).enhance(2.4)
    contrast = ImageEnhance.Contrast(sharpened).enhance(2.0)
    variants.append(("upscaled_contrast", contrast))

    binary = contrast.point(lambda value: 255 if value > 168 else 0)
    variants.append(("binary", binary))

    dark_mode = ImageOps.invert(upscaled)
    dark_mode = ImageEnhance.Contrast(dark_mode).enhance(1.8)
    dark_binary = dark_mode.point(lambda value: 255 if value > 150 else 0)
    variants.append(("dark_binary", dark_binary))

    denoised = contrast.filter(ImageFilter.MedianFilter(size=3))
    variants.append(("denoised", denoised))

    output_paths: list[Path] = []
    for name, variant in variants:
        path = temp_dir / f"{name}.png"
        variant.save(path)
        output_paths.append(path)
    return output_paths


def _run_tesseract(image_path: Path, language: str, psm: int) -> str:
    command = [
        "tesseract",
        str(image_path),
        "stdout",
        "--oem",
        "3",
        "--psm",
        str(psm),
        "-c",
        "preserve_interword_spaces=1",
    ]
    if language:
        command.extend(["-l", language])
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        return ""
    return result.stdout.strip()


def _score_text(text: str) -> float:
    if not text:
        return 0.0
    useful = 0
    code_chars = 0
    for char in text:
        if char.isalnum() or "\u4e00" <= char <= "\u9fff":
            useful += 1
        if char in "{}[]()<>=_-/\\.:;,'\"`|*#@":
            code_chars += 1
    line_bonus = min(text.count("\n"), 12) * 0.8
    return useful + code_chars * 0.4 + line_bonus


class OCRResultDialog(QDialog):
    def __init__(self, text: str, translation_config: TranslationConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("文字识别结果")
        self.resize(640, 420)
        self._translation_config = translation_config
        self._translated_text = ""
        self.setStyleSheet(
            "QDialog { background: #f8fafc; color: #0f172a; }"
            "QLabel { color: #334155; font-weight: 600; }"
            "QPlainTextEdit { background: white; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 10px; padding: 10px; selection-background-color: #bfdbfe; }"
            "QPushButton { background: #e2e8f0; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 8px; padding: 6px 12px; }"
            "QPushButton:hover { background: #cbd5e1; }"
        )

        original_label = QLabel("识别文本", self)
        self._text_edit = QPlainTextEdit(self)
        self._text_edit.setPlainText(text)
        self._text_edit.setReadOnly(False)
        self._text_edit.setPlaceholderText("未识别到文字")

        translation_label = QLabel("翻译结果", self)
        self._translation_edit = QPlainTextEdit(self)
        self._translation_edit.setReadOnly(False)
        self._translation_edit.setPlaceholderText("点击“翻译文本”后会显示结果")

        buttons = QDialogButtonBox(self)
        copy_button = buttons.addButton("复制文本", QDialogButtonBox.ButtonRole.ActionRole)
        translate_button = buttons.addButton("翻译文本", QDialogButtonBox.ButtonRole.ActionRole)
        copy_translation_button = buttons.addButton("复制翻译", QDialogButtonBox.ButtonRole.ActionRole)
        close_button = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        copy_button.clicked.connect(self._copy_text)
        translate_button.clicked.connect(self._translate_text)
        copy_translation_button.clicked.connect(self._copy_translation)
        close_button.clicked.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(original_label)
        layout.addWidget(self._text_edit)
        layout.addWidget(translation_label)
        layout.addWidget(self._translation_edit)
        layout.addWidget(buttons, alignment=Qt.AlignmentFlag.AlignRight)

        if self._translation_config.auto_translate_ocr and text.strip():
            self._translate_text()

    def _copy_text(self) -> None:
        QApplication.clipboard().setText(self._text_edit.toPlainText())

    def _copy_translation(self) -> None:
        QApplication.clipboard().setText(self._translation_edit.toPlainText())

    def _translate_text(self) -> None:
        source = self._text_edit.toPlainText().strip()
        if not source:
            self._translation_edit.clear()
            return
        try:
            self._translated_text = translate_text(source, self._translation_config)
        except Exception as exc:
            QMessageBox.warning(self, "翻译失败", str(exc))
            return
        self._translation_edit.setPlainText(self._translated_text)
