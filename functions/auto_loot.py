from __future__ import annotations

import os
import time

import cv2
import numpy as np

from core.config import RESOURCE_DIR
from core.input_simulator import InputSimulator
from core.screen_capture import ScreenCapture, is_valid_region, load_image_with_mask
from core.worker import BaseWorker

SURROUNDING_TILE_OFFSETS = [
    (0, -1),
    (1, -1),
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
]


def resolve_icon_path(path: str | None) -> str:
    if not path:
        return path
    if os.path.isabs(path):
        return path
    return os.path.join(RESOURCE_DIR, path)


def point_in_region(x: int, y: int, region) -> bool:
    rx, ry, rw, rh = region
    return rx <= x < rx + rw and ry <= y < ry + rh


class AutoLootWorker(BaseWorker):
    name_label = "auto_loot"

    def setup(self) -> None:
        self.hwnd = self.config.get("_background_hwnd")

        self.character_point = self.config.get("character_point")
        if not self.character_point or len(self.character_point) != 2:
            raise ValueError(
                "Posição do personagem não calibrada. Selecione esse ponto antes de iniciar."
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

        self.tile_size_px = max(1, int(self.config.get("tile_size_px", 32)))
        self.open_corpse_delay_s = float(self.config.get("open_corpse_delay_s", 0.6))
        self.check_interval = float(self.config.get("check_interval", 0.3))
        self.loot_scan_timeout_s = float(self.config.get("loot_scan_timeout_s", 3.0))
        self.max_loot_passes = int(self.config.get("max_loot_passes", 10))
        self.corpse_recheck_cooldown_s = float(self.config.get("corpse_recheck_cooldown_s", 3.0))
        self.click_jitter = int(self.config.get("click_jitter", 2))
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

    def _collect_loot(self) -> int:
        if not self.request_floor(timeout=5.0):
            self.log("Coleta de loot cancelada: outra rotina de prioridade maior não liberou o chão.")
            return 0
        try:
            return self._collect_loot_passes()
        finally:
            self.release_floor()

    def _sweep_surrounding_tiles(self) -> None:
        if not self.request_floor(timeout=5.0):
            self.log("Varredura de corpos cancelada: outra rotina de prioridade maior não liberou o chão.")
            return
        try:
            cx, cy = int(self.character_point[0]), int(self.character_point[1])
            for dx, dy in SURROUNDING_TILE_OFFSETS:
                if not self.wait_for_higher_priority():
                    return
                x = cx + dx * self.tile_size_px
                y = cy + dy * self.tile_size_px
                self.mouse.click(x, y, button="right", jitter=self.click_jitter)
                if not self.sleep(self.open_corpse_delay_s):
                    return

                frame = self.capture.grab(self.corpse_region)
                if self._find_loot_item(frame) is None:
                    continue

                self.log(f"Corpo aberto em x={x} y={y} - loot encontrado.")
                self._collect_loot_passes()
        finally:
            self.release_floor()

    def loop(self) -> None:
        was_engaged = False
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
                else False
            )

            if was_engaged and not target_engaged:
                self.log("Combate encerrado - varrendo os SQMs ao redor em busca de corpo.")
                self._sweep_surrounding_tiles()
                corpse_idle_until = None
            was_engaged = target_engaged

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
