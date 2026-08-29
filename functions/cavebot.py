from __future__ import annotations

import os

import cv2
import numpy as np
import win32gui

from core import background_input
from core.config import RESOURCE_DIR
from core.input_simulator import InputSimulator
from core.screen_capture import ScreenCapture, is_valid_region, load_image
from core.worker import BaseWorker


def resolve_icon_path(path: str | None) -> str:
    if not path:
        return path
    if os.path.isabs(path):
        return path
    return os.path.join(RESOURCE_DIR, path)


def point_in_region(x: int, y: int, region) -> bool:
    rx, ry, rw, rh = region
    return rx <= x < rx + rw and ry <= y < ry + rh


def region_within(inner, outer) -> bool:
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    return ix >= ox and iy >= oy and ix + iw <= ox + ow and iy + ih <= oy + oh


class CavebotWorker(BaseWorker):
    name_label = "cavebot"

    def setup(self) -> None:
        self.hwnd = self.config.get("_background_hwnd")
        if not self.hwnd or not win32gui.IsWindow(self.hwnd):
            raise ValueError(
                "Janela do jogo (modo background) não configurada ou não encontrada. "
                "Configure em Configurações > Modo background."
            )

        self.waypoints = list(self.config.get("waypoints") or [])
        if not self.waypoints:
            raise ValueError("Nenhum ponto de rota configurado. Adicione ao menos um ponto no Cavebot.")

        self.minimap_region = self.config.get("minimap_region")
        if not is_valid_region(self.minimap_region):
            raise ValueError("Região do mini mapa não calibrada. Capture a região do mini mapa antes de iniciar.")

        self.confidence = float(self.config.get("confidence", 0.85))
        self.check_interval = float(self.config.get("check_interval", 0.3))
        self.search_timeout = float(self.config.get("search_timeout", 5.0))
        self.max_search_failures = int(self.config.get("max_search_failures", 3))
        self.click_jitter = int(self.config.get("click_jitter", 2))

        self.icons: dict[str, np.ndarray] = {}
        for waypoint in self.waypoints:
            path = resolve_icon_path(waypoint.get("icon"))
            if not path:
                raise ValueError("Ponto da rota sem ícone configurado - recadastre o ponto.")
            if path in self.icons:
                continue
            icon = load_image(path)
            if icon is None:
                raise ValueError(f"Ícone do ponto não encontrado ou inválido: {waypoint.get('icon')}")
            self.icons[path] = icon

        self.min_region_width = max(icon.shape[1] for icon in self.icons.values())
        self.min_region_height = max(icon.shape[0] for icon in self.icons.values())
        if self.minimap_region[2] < self.min_region_width or self.minimap_region[3] < self.min_region_height:
            raise ValueError(
                "Região do mini mapa é menor que o maior ícone configurado - recalibre a região do mini mapa."
            )

        self.capture = ScreenCapture()
        self.mouse = InputSimulator(background_hwnd=self.hwnd, on_fallback=self.log)
        self.register_with_coordinator("cavebot")

        self.current_index = 0

        self.log(
            f"Cavebot iniciado ({len(self.waypoints)} ponto(s) na rota, "
            f"backend={InputSimulator.backend_name()})."
        )

    def teardown(self) -> None:
        capture = getattr(self, "capture", None)
        if capture is not None:
            capture.close()
        self.unregister_from_coordinator()
        self.log(f"Cavebot finalizado. Pontos percorridos na sessão: {self.counter}.")

    def _locate_icon(self, frame: np.ndarray, icon: np.ndarray, confidence: float) -> tuple[int, int] | None:
        if frame.shape[0] < icon.shape[0] or frame.shape[1] < icon.shape[1]:
            return None
        result = cv2.matchTemplate(frame, icon, cv2.TM_CCOEFF_NORMED)
        _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(result)
        if max_val < confidence:
            return None
        height, width = icon.shape[:2]
        return max_loc[0] + width // 2, max_loc[1] + height // 2

    def _locate_and_click(self, icon: np.ndarray, confidence: float, client_rect) -> str:
        match = None
        remaining_search = self.search_timeout
        while remaining_search > 0:
            if not self.wait_for_higher_priority():
                return "stopped"
            frame = self.capture.grab(self.minimap_region)
            match = self._locate_icon(frame, icon, confidence)
            if match:
                break
            step = min(self.check_interval, remaining_search)
            if not self.sleep(step):
                return "stopped"
            remaining_search -= step

        if match is None:
            return "not_found"

        rel_x, rel_y = match
        abs_x = int(self.minimap_region[0]) + rel_x
        abs_y = int(self.minimap_region[1]) + rel_y

        if not point_in_region(abs_x, abs_y, self.minimap_region) or not point_in_region(abs_x, abs_y, client_rect):
            return "out_of_bounds"

        if not self.wait_for_higher_priority():
            return "stopped"
        if not self.request_floor(timeout=5.0):
            return "floor_denied"
        try:
            self.mouse.click(abs_x, abs_y, button="left", jitter=self.click_jitter)
        finally:
            self.release_floor()
        return "clicked"

    def loop(self) -> None:
        region_indisponivel_avisado = False
        search_failures = 0

        while not self.stopped:
            if not self.wait_for_higher_priority():
                return

            if not win32gui.IsWindow(self.hwnd):
                raise RuntimeError(
                    "Janela do jogo não encontrada (hwnd inválido) - reabra o jogo e reconfigure o modo background."
                )

            client_rect = background_input.client_screen_rect(self.hwnd)
            if client_rect is None or not region_within(self.minimap_region, client_rect):
                if not region_indisponivel_avisado:
                    self.log(
                        "Janela do jogo minimizada ou região do mini mapa fora da área visível - "
                        "aguardando ela voltar para continuar a rota."
                    )
                    region_indisponivel_avisado = True
                if not self.sleep(self.check_interval):
                    return
                continue
            region_indisponivel_avisado = False

            waypoint = self.waypoints[self.current_index]
            icon_path = resolve_icon_path(waypoint.get("icon"))
            icon = self.icons.get(icon_path)
            wait_s = float(waypoint.get("wait_s", 0.0) or 0.0)
            confidence = float(waypoint.get("confidence") or self.confidence)
            icon_nome = os.path.basename(waypoint.get("icon") or "?")
            ponto_label = f"{self.current_index + 1}/{len(self.waypoints)} ({icon_nome})"

            outcome = self._locate_and_click(icon, confidence, client_rect)
            if outcome == "stopped":
                return
            if outcome != "clicked":
                search_failures += 1
                if outcome == "not_found":
                    motivo = f"ícone não encontrado no mini mapa em {self.search_timeout:.0f}s"
                elif outcome == "floor_denied":
                    motivo = "outra rotina de prioridade maior está agindo"
                else:
                    motivo = "coordenada calculada fora da região do mini mapa ou da janela do jogo"
                self.log(f"Ponto {ponto_label}: {motivo} (falha {search_failures}/{self.max_search_failures}).")
                if search_failures >= self.max_search_failures:
                    self.log(
                        f"Ponto {ponto_label}: desistindo após {self.max_search_failures} tentativas - "
                        "seguindo para o próximo ponto da rota."
                    )
                    search_failures = 0
                    self.current_index = (self.current_index + 1) % len(self.waypoints)
                continue

            search_failures = 0
            self.bump_counter()
            self.log(f"Ponto {ponto_label}: clique enviado (#{self.counter}). Aguardando {wait_s:.0f}s.")

            remaining = wait_s
            chegou = True
            while remaining > 0:
                if self.coordinator and self.coordinator.should_pause(self._coordinator_name):
                    if not self.wait_for_higher_priority():
                        return
                    self.log(f"Ponto {ponto_label}: combate encerrado, retomando o trajeto.")
                    client_rect = background_input.client_screen_rect(self.hwnd)
                    if client_rect is None:
                        chegou = False
                        break
                    outcome = self._locate_and_click(icon, confidence, client_rect)
                    if outcome == "stopped":
                        return
                    if outcome != "clicked":
                        self.log(f"Ponto {ponto_label}: não foi possível retomar o trajeto após o combate - tentando de novo.")
                        chegou = False
                        break
                    continue
                chunk = min(0.2, remaining)
                if not self.sleep(chunk):
                    return
                remaining -= chunk

            if chegou:
                self.current_index = (self.current_index + 1) % len(self.waypoints)
