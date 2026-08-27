from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

_IGNORED_KEYS = {
    Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta,
    Qt.Key_CapsLock, Qt.Key_NumLock, Qt.Key_ScrollLock,
}

_KEY_MAP = {
    Qt.Key_Return: "enter",
    Qt.Key_Enter: "enter",
    Qt.Key_Escape: "esc",
    Qt.Key_Backspace: "backspace",
    Qt.Key_Delete: "delete",
    Qt.Key_Tab: "tab",
    Qt.Key_Pause: "pause",
    Qt.Key_Up: "up",
    Qt.Key_Down: "down",
    Qt.Key_Left: "left",
    Qt.Key_Right: "right",
    Qt.Key_PageUp: "pageup",
    Qt.Key_PageDown: "pagedown",
    Qt.Key_Home: "home",
    Qt.Key_End: "end",
    Qt.Key_Space: "space",
}


class HotkeyButton(QPushButton):
    def __init__(self, initial: str = "", on_change=None, parent=None):
        super().__init__(parent)
        self.on_change = on_change
        self._value = initial or ""
        self._capturing = False
        self._refresh_label()
        self.clicked.connect(self._start_capture)

    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        self._value = value or ""
        self._refresh_label()

    def _refresh_label(self) -> None:
        self.setText((self._value or "-").upper())

    def _start_capture(self) -> None:
        self._capturing = True
        self.setText("Pressione uma tecla...")
        self.setFocus()
        self.grabKeyboard()

    def focusOutEvent(self, event) -> None:
        if self._capturing:
            self._cancel_capture()
        super().focusOutEvent(event)

    def _cancel_capture(self) -> None:
        self._capturing = False
        self.releaseKeyboard()
        self._refresh_label()

    def keyPressEvent(self, event) -> None:
        if not self._capturing:
            super().keyPressEvent(event)
            return
        key = event.key()
        if key in _IGNORED_KEYS:
            return
        name = self._normalize(key, event.text())
        if not name:
            return
        self._capturing = False
        self.releaseKeyboard()
        self._value = name
        self._refresh_label()
        if self.on_change:
            self.on_change(name)

    @staticmethod
    def _normalize(key: int, text: str) -> str | None:
        if Qt.Key_F1 <= key <= Qt.Key_F24:
            return f"f{key - Qt.Key_F1 + 1}"
        if key in _KEY_MAP:
            return _KEY_MAP[key]
        if text and len(text) == 1 and text.isprintable():
            return text.lower()
        return None
