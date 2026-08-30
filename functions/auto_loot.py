from __future__ import annotations

import os
import time

import cv2
import numpy as np

from core.config import RESOURCE_DIR
from core.input_simulator import InputSimulator
from core.screen_capture import ScreenCapture, is_valid_region, load_image_with_mask
from core.worker import BaseWorker
from functions.target import color_mask


def resolve_icon_path(path: str | None) -> str:
    if not path:
        return path
    if os.path.isabs(path):
        return path
    return os.path.join(RESOURCE_DIR, path)


def point_in_region(x: int, y: int, region) -> bool:
    rx, ry, rw, rh = region
    return rx <= x < rx + rw and ry <= y < ry + rh


def sample_dominant_color(frame: np.ndarray) -> tuple[int, int, int]:
    mean_bgr = frame.reshape(-1, 3).mean(axis=0)
    b, g, r = mean_bgr
    return int(round(r)), int(round(g)), int(round(b))


def _find_marker_square(mask: np.ndarray) -> tuple[int, int] | None:
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if not contours or hierarchy is None:
        return None
    hierarchy = hierarchy[0]
    best = None
    best_area = 0
    for i, contour in enumerate(contours):
        has_hole = hierarchy[i][2] != -1
        if not has_hole:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if w < 6 or h < 6:
            continue
        aspect = w / h
        if not (0.65 <= aspect <= 1.55):
            continue

        box_area = w * h
        contour_area = cv2.contourArea(contour)
        extent = contour_area / box_area if box_area > 0 else 0
        if extent < 0.75:
            continue

        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.04 * perimeter, True)
        if len(approx) > 6:
            continue

        if box_area > best_area:
            best_area = box_area
            best = (x + w // 2, y + h // 2)
    return best


def attack_color_centroid(
    frame: np.ndarray,
    rgb: tuple[int, int, int] = (254, 0, 0),
    tolerance: int = 6,
    min_pixels: int = 3,
) -> tuple[int, int] | None:
    mask = color_mask(frame, rgb, tolerance)
    if mask is None:
        return None

    marker = _find_marker_square(mask)
    if marker is not None:
        return marker

    if int(np.count_nonzero(mask)) < min_pixels:
        return None
    points = cv2.findNonZero(mask)
    if points is None:
        return None
    x, y = np.mean(points.reshape(-1, 2), axis=0)
    return int(round(x)), int(round(y))


class AutoLootWorker(BaseWorker):
    name_label = "auto_loot"

    def setup(self) -> None:
        self.hwnd = self.config.get("_background_hwnd")

        self.death_watch_region = self.config.get("death_watch_region")
        if not is_valid_region(self.death_watch_region):
            raise ValueError(
                "Área de monitoramento da morte não calibrada. Capture essa região antes de iniciar."
            )

        self.corpse_region = self.config.get("corpse_region")
        if not is_valid_region(self.corpse_region):
            raise ValueError(
                "Região da bag de origem (corpo) não calibrada. Capture essa região antes de iniciar."
            )

        self.destination_point = self.config.get("destination_point")
        if not self.destination_point or len(self.destination_point) != 2:
            raise ValueError("Ponto da bag de destino não calibrado. Selecione esse ponto antes de iniciar.")

        if point_in_region(
            int(self.destination_point[0]), int(self.destination_point[1]), self.corpse_region
        ):
            raise ValueError(
                "O ponto da bag de destino cai dentro da região da bag de origem (corpo) - as duas "
                "precisam estar em posições diferentes na tela, senão o AutoLoot pode confundir item já "
                "guardado no destino com item ainda no corpo. Recalibre uma das duas."
            )

        self.loot_items = list(self.config.get("loot_items") or [])
        if not self.loot_items:
            raise ValueError("Nenhum item de loot configurado. Adicione ao menos um item antes de iniciar.")

        rgb = self.config.get("attack_color_rgb") or [254, 0, 0]
        self.attack_rgb = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        self.attack_tolerance = int(self.config.get("attack_color_tolerance", 6))
        self.attack_min_pixels = int(self.config.get("attack_color_min_pixels", 3))

        self.open_corpse_delay_s = float(self.config.get("open_corpse_delay_s", 0.6))
        self.check_interval = float(self.config.get("check_interval", 0.3))
        self.death_confirm_delay_s = float(self.config.get("death_confirm_delay_s", 0.6))
        self.loot_scan_timeout_s = float(self.config.get("loot_scan_timeout_s", 3.0))
        self.max_loot_passes = int(self.config.get("max_loot_passes", 10))
        self.corpse_recheck_cooldown_s = float(self.config.get("corpse_recheck_cooldown_s", 3.0))
        self.click_jitter = int(self.config.get("click_jitter", 2))
        self.open_corpse_corner_offset = int(self.config.get("open_corpse_corner_offset", 0))
        self.stuck_item_max_retries = max(1, int(self.config.get("stuck_item_max_retries", 3)))

        self._cap_warning_shown = False

        self.icons: dict[str, tuple[np.ndarray, np.ndarray | None]] = {}
        for item in self.loot_items:
            raw_path = item.get("icon")
            if not raw_path:
                raise ValueError("Item de loot sem ícone configurado - recadastre o item.")
            path = resolve_icon_path(raw_path)
            if path in self.icons:
                continue
            loaded = load_image_with_mask(path)
            if loaded is None:
                raise ValueError(f"Ícone do item de loot não encontrado ou inválido: {raw_path}")
            self.icons[path] = loaded

        self.capture = ScreenCapture()
        self.mouse = InputSimulator(background_hwnd=self.hwnd, on_fallback=self.log)
        self.register_with_coordinator("auto_loot")

        self.log(
            f"AutoLoot iniciado ({len(self.loot_items)} item(ns) de loot configurado(s), "
            f"backend={InputSimulator.backend_name()})."
        )

    def teardown(self) -> None:
        capture = getattr(self, "capture", None)
        if capture is not None:
            capture.close()
        self.unregister_from_coordinator()
        self.log(f"AutoLoot finalizado. Itens recolhidos na sessão: {self.counter}.")

    def _locate_icon(
        self,
        frame: np.ndarray,
        icon: np.ndarray,
        confidence: float,
        mask: np.ndarray | None = None,
    ) -> tuple[int, int] | None:
        if frame.shape[0] < icon.shape[0] or frame.shape[1] < icon.shape[1]:
            return None
        if mask is not None:
            result = cv2.matchTemplate(frame, icon, cv2.TM_CCOEFF_NORMED, mask=mask)
        else:
            result = cv2.matchTemplate(frame, icon, cv2.TM_CCOEFF_NORMED)
        _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(result)
        if max_val < confidence:
            return None
        height, width = icon.shape[:2]
        return max_loc[0] + width // 2, max_loc[1] + height // 2

    def _find_loot_item(self, frame: np.ndarray) -> tuple[dict, int, int] | None:
        for item in self.loot_items:
            loaded = self.icons.get(resolve_icon_path(item.get("icon")))
            if loaded is None:
                continue
            icon, mask = loaded
            confidence = float(item.get("confidence", 0.85))
            match = self._locate_icon(frame, icon, confidence, mask)
            if match is not None:
                return item, match[0], match[1]
        return None

    def _loot_pass(self) -> bool:
        remaining = self.loot_scan_timeout_s
        while True:
            if not self.wait_for_higher_priority():
                return False

            frame = self.capture.grab(self.corpse_region)
            found = self._find_loot_item(frame)
            if found is not None:
                item, rel_x, rel_y = found
                src_x = int(self.corpse_region[0]) + rel_x
                src_y = int(self.corpse_region[1]) + rel_y
                dest_x, dest_y = int(self.destination_point[0]), int(self.destination_point[1])

                stuck_attempts = 0
                while True:
                    self.mouse.drag(
                        src_x, src_y, dest_x, dest_y,
                        from_jitter=self.click_jitter, to_jitter=self.click_jitter,
                    )
                    if not self.sleep(self.check_interval):
                        return False

                    after_frame = self.capture.grab(self.corpse_region)
                    still_found = self._find_loot_item(after_frame)
                    stuck = (
                        still_found is not None
                        and abs(still_found[1] - rel_x) <= self.click_jitter + 2
                        and abs(still_found[2] - rel_y) <= self.click_jitter + 2
                    )
                    if not stuck:
                        break

                    stuck_attempts += 1
                    if stuck_attempts >= self.stuck_item_max_retries:
                        self.log(
                            f"Item continua na mesma posição após {stuck_attempts} tentativas - "
                            "provável capacidade (cap) ou bag de destino cheia. Parando essa passada."
                        )
                        if not self._cap_warning_shown:
                            self._cap_warning_shown = True
                            self.warn_popup(
                                "AutoLoot não conseguiu mover um item pro destino - verifique se a "
                                "capacidade (cap) ou a bag de destino estão cheias."
                            )
                        return False

                    if not self.wait_for_higher_priority():
                        return False

                self.bump_counter()
                nome = item.get("nome") or os.path.basename(item.get("icon") or "?")
                self.log(f"Item recolhido: {nome} (#{self.counter}).")
                return True

            if remaining <= 0:
                return False
            step = min(self.check_interval, remaining)
            if not self.sleep(step):
                return False
            remaining -= step

    def _collect_loot_passes(self) -> int:
        collected = 0
        for _ in range(self.max_loot_passes):
            if not self.wait_for_higher_priority():
                return collected
            if not self._loot_pass():
                if not self.stopped:
                    self.log("Nada mais encontrado no corpo.")
                return collected
            collected += 1
        self.log(f"Limite de {self.max_loot_passes} passada(s) de loot atingido - encerrando por segurança.")
        return collected

    def _open_corpse_and_collect(self, xy: tuple[int, int]) -> None:
        if not self.request_floor(timeout=5.0):
            self.log("Sequência de loot cancelada: outra rotina de prioridade maior não liberou o chão.")
            return
        try:
            if not self.wait_for_higher_priority():
                return

            recheck_frame = self.capture.grab(self.death_watch_region)
            if attack_color_centroid(
                recheck_frame, self.attack_rgb, self.attack_tolerance, self.attack_min_pixels
            ) is not None:
                self.log("Falso alarme - cor de ataque reapareceu antes do clique, corpo não será aberto.")
                return

            x, y = xy
            x += self.open_corpse_corner_offset
            y += self.open_corpse_corner_offset
            self.mouse.click(x, y, button="right", jitter=self.click_jitter)
            self.log(f"Corpo aberto em x={x} y={y}.")
            if not self.sleep(self.open_corpse_delay_s):
                return
            self._collect_loot_passes()
        finally:
            self.release_floor()

    def _collect_loot(self) -> int:
        if not self.request_floor(timeout=5.0):
            self.log("Coleta de loot cancelada: outra rotina de prioridade maior não liberou o chão.")
            return 0
        try:
            return self._collect_loot_passes()
        finally:
            self.release_floor()

    def loop(self) -> None:
        last_seen_xy: tuple[int, int] | None = None
        absent_since: float | None = None
        corpse_idle_until: float | None = None

        while not self.stopped:
            if not self.wait_while_paused():
                return

            if (
                self.coordinator
                and self._coordinator_name
                and self.coordinator.should_pause(self._coordinator_name)
            ):
                self.coordinator.confirm_paused(self._coordinator_name)

            target_engaged = (
                self.coordinator.is_engaged("target")
                if self.coordinator and self.coordinator.is_active("target")
                else True
            )

            death_frame = self.capture.grab(self.death_watch_region)
            centroid = attack_color_centroid(
                death_frame, self.attack_rgb, self.attack_tolerance, self.attack_min_pixels
            )

            if centroid is not None:
                if last_seen_xy is not None or target_engaged:
                    last_seen_xy = (
                        int(self.death_watch_region[0]) + centroid[0],
                        int(self.death_watch_region[1]) + centroid[1],
                    )
                absent_since = None
            elif last_seen_xy is not None:
                now = time.monotonic()
                if absent_since is None:
                    absent_since = now
                elif now - absent_since >= self.death_confirm_delay_s:
                    self.log("Morte detectada - abrindo corpo e coletando o loot.")
                    self._open_corpse_and_collect(last_seen_xy)
                    last_seen_xy = None
                    absent_since = None
                    corpse_idle_until = None

            now = time.monotonic()
            if corpse_idle_until is None or now >= corpse_idle_until:
                corpse_frame = self.capture.grab(self.corpse_region)
                if self._find_loot_item(corpse_frame) is not None:
                    collected = self._collect_loot()
                    corpse_idle_until = (
                        None if collected > 0 else time.monotonic() + self.corpse_recheck_cooldown_s
                    )

            if not self.sleep(self.check_interval):
                return
