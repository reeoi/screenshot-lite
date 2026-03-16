from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal
from pynput import keyboard


@dataclass(slots=True)
class HotkeyRegistrationResult:
    success: bool
    message: str = ""


class GlobalHotkeyManager(QObject):
    regionTriggered = Signal()
    fullscreenTriggered = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._listener: keyboard.GlobalHotKeys | None = None

    def register(self, region_shortcut: str, fullscreen_shortcut: str) -> HotkeyRegistrationResult:
        self.unregister()
        mappings: dict[str, object] = {}

        region_binding = self._to_pynput_shortcut(region_shortcut)
        fullscreen_binding = self._to_pynput_shortcut(fullscreen_shortcut)
        if not region_binding or not fullscreen_binding:
            return HotkeyRegistrationResult(False, "快捷键格式无效")

        mappings[region_binding] = self.regionTriggered.emit
        mappings[fullscreen_binding] = self.fullscreenTriggered.emit

        try:
            self._listener = keyboard.GlobalHotKeys(mappings)
            self._listener.start()
        except Exception as exc:
            self._listener = None
            return HotkeyRegistrationResult(False, f"全局快捷键注册失败：{exc}")
        return HotkeyRegistrationResult(True)

    def unregister(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _to_pynput_shortcut(self, shortcut: str) -> str:
        if not shortcut:
            return ""
        parts = [part.strip() for part in shortcut.replace("+", "+").split("+") if part.strip()]
        mapped_parts: list[str] = []
        special = {
            "ctrl": "<ctrl>",
            "control": "<ctrl>",
            "alt": "<alt>",
            "shift": "<shift>",
            "meta": "<cmd>",
            "super": "<cmd>",
            "win": "<cmd>",
            "return": "<enter>",
            "enter": "<enter>",
            "esc": "<esc>",
            "escape": "<esc>",
            "space": "<space>",
            "tab": "<tab>",
        }
        for part in parts:
            lower = part.lower()
            if lower in special:
                mapped_parts.append(special[lower])
                continue
            if lower.startswith("f") and lower[1:].isdigit():
                mapped_parts.append(f"<{lower}>")
                continue
            if len(lower) == 1:
                mapped_parts.append(lower)
                continue
            return ""
        return "+".join(mapped_parts)
