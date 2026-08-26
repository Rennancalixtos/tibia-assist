from __future__ import annotations

from typing import Sequence

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

import mss


Region = Sequence[int]


class ScreenCapture:
    def __init__(self) -> None:
        self._sct = mss.mss()

    def grab(self, region: Region | None = None) -> np.ndarray:
        if region is None:
            monitor = self._sct.monitors[0]
        else:
            x, y, w, h = region
            monitor = {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
        raw = self._sct.grab(monitor)
        frame = np.array(raw)
        return frame[:, :, :3]

    def grab_fullscreen(self) -> np.ndarray:
        return self.grab(None)

    def virtual_screen_size(self) -> tuple[int, int, int, int]:
        m = self._sct.monitors[0]
        return m["left"], m["top"], m["width"], m["height"]

    def close(self) -> None:
        try:
            self._sct.close()
        except Exception:
            pass

    def __enter__(self) -> "ScreenCapture":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def save_image(path: str, image: np.ndarray) -> None:
    if cv2 is None:
        raise RuntimeError("opencv-python nao esta instalado")
    cv2.imwrite(path, image)


def load_image(path: str) -> np.ndarray | None:
    if cv2 is None:
        raise RuntimeError("opencv-python nao esta instalado")
    return cv2.imread(path, cv2.IMREAD_COLOR)


def is_valid_region(region: Region | None) -> bool:
    return (
        isinstance(region, (list, tuple))
        and len(region) == 4
        and int(region[2]) > 0
        and int(region[3]) > 0
    )
