from __future__ import annotations

import time

from core.input_simulator import InputSimulator
from core.screen_capture import ScreenCapture, is_valid_region, load_image
from core.worker import BaseWorker
from functions.rune_maker import OCRUnavailable, configure_tesseract, read_number
from functions.target import (
    attack_color_present,
    battle_list_empty_score,
    name_similarity,
    normalize_name,
    read_name,
)


def creature_name_present(ocr_text: str, creature_name: str, threshold: float) -> bool:
    normalized_text = normalize_name(ocr_text)
    normalized_name = normalize_name(creature_name)
    if not normalized_name or not normalized_text:
        return False
    if normalized_name in normalized_text:
        return True
    text_words = normalized_text.split()
    name_words = normalized_name.split()
    window = len(name_words)
    if window == 0 or len(text_words) < window:
        return name_similarity(normalized_text, normalized_name) >= threshold
    best = 0.0
    for i in range(len(text_words) - window + 1):
        candidate = " ".join(text_words[i:i + window])
        best = max(best, name_similarity(candidate, normalized_name))
    return best >= threshold


class TrainingWorker(BaseWorker):
    name_label = "training"

    def setup(self) -> None:
        self.capture = ScreenCapture()
        self.mouse = InputSimulator(
            background_hwnd=self.config.get("_background_hwnd"),
            on_fallback=self.log,
        )
        self.register_with_coordinator("training")

        self.battle_list_region = self.config.get("battle_list_region")
        if not is_valid_region(self.battle_list_region):
            raise ValueError("Região da Battle List não configurada.")

        self.empty_template = self._load_template("training_battle_empty_template")
        if self.empty_template is None:
            raise ValueError("Modelo de lista vazia não calibrado.")
        self.empty_threshold = float(self.config.get("empty_match_threshold", 0.85))

        rgb = self.config.get("attack_color_rgb") or [254, 0, 0]
        self.attack_rgb = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        self.attack_tolerance = int(self.config.get("attack_color_tolerance", 6))
        self.attack_min_pixels = int(self.config.get("attack_color_min_pixels", 3))

        self.attack_key = (self.config.get("attack_key") or "space").strip().lower()
        if not self.attack_key:
            raise ValueError("Tecla de ataque não configurada.")
        self.attack_check_delay = float(self.config.get("attack_check_delay", 0.5))

        self.creature_name = (self.config.get("creature_name") or "").strip()
        if not self.creature_name:
            raise ValueError("Nome do monstro de treino não configurado.")
        self.name_match_threshold = float(self.config.get("name_match_threshold", 0.80))

        self.missing_retries = max(1, int(self.config.get("missing_retries", 5)))
        self.missing_retry_interval = float(self.config.get("missing_retry_interval", 2.0))
        self._missing_count = 0

        self.cast_spell_enabled = bool(self.config.get("cast_spell_enabled", False))
        self._next_spell_at = 0.0
        if self.cast_spell_enabled:
            self.spell_hotkey = (self.config.get("spell_hotkey") or "").strip()
            if not self.spell_hotkey:
                raise ValueError("Tecla de atalho da magia de ataque não configurada.")
            self.check_mana = bool(self.config.get("check_mana", True))
            if self.check_mana and not is_valid_region(self.config.get("mana_region")):
                raise ValueError("Região de OCR da mana (magia de ataque) não configurada.")

        self.anti_afk_enabled = bool(self.config.get("anti_afk_enabled", False))
        self.anti_afk_interval = float(self.config.get("anti_afk_interval_minutes", 10) or 10) * 60
        self._next_anti_afk_at = time.monotonic() + self.anti_afk_interval

        self._last_warning = ""
        self._session_started_at = time.monotonic()
        self._last_elapsed_emit = 0.0

        configure_tesseract(on_progress=self.log)

        self.log(
            f"Training iniciado (alvo='{self.creature_name}', tecla de ataque='{self.attack_key}', "
            f"backend={InputSimulator.backend_name()})."
        )

    def teardown(self) -> None:
        capture = getattr(self, "capture", None)
        if capture is not None:
            capture.close()
        self.unregister_from_coordinator()
        elapsed = self._format_elapsed(time.monotonic() - self._session_started_at)
        self.log(f"Training finalizado. Tempo total treinando: {elapsed}.")

    def _load_template(self, key: str):
        path = self.config.get(key)
        if not path:
            return None
        try:
            return load_image(path)
        except Exception:
            return None

    def warn_once(self, message: str) -> None:
        if message != self._last_warning:
            self.log(message)
            self._last_warning = message

    def maybe_send_anti_afk(self) -> None:
        if not self.anti_afk_enabled or time.monotonic() < self._next_anti_afk_at:
            return
        key_a = (self.config.get("anti_afk_key_a") or "up").strip().lower()
        key_b = (self.config.get("anti_afk_key_b") or "down").strip().lower()
        if self.request_floor(timeout=5.0):
            try:
                self.mouse.press_key(key_a)
                time.sleep(InputSimulator.random_delay(0.10, 0.25))
                self.mouse.press_key(key_b)
            finally:
                self.release_floor()
            self.log("Anti-AFK: movimento leve enviado.")
        self._next_anti_afk_at = time.monotonic() + self.anti_afk_interval

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        seconds = max(0, int(seconds))
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _emit_elapsed(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_elapsed_emit < 1.0:
            return
        self._last_elapsed_emit = now
        self.emit("elapsed", self._format_elapsed(now - self._session_started_at))

    def battle_list_empty_score(self) -> float | None:
        frame = self.capture.grab(self.battle_list_region)
        return battle_list_empty_score(frame, self.empty_template)

    def is_battle_list_empty(self) -> bool:
        score = self.battle_list_empty_score()
        if score is None:
            self.warn_once(
                "AVISO: modelo de lista vazia maior que a região configurada - "
                "recalibre a região da Battle List ou o modelo."
            )
            return False
        return score >= self.empty_threshold

    def is_attacking(self) -> bool:
        frame = self.capture.grab(self.battle_list_region)
        return attack_color_present(frame, self.attack_rgb, self.attack_tolerance, self.attack_min_pixels)

    def read_battle_list_text(self) -> str:
        frame = self.capture.grab(self.battle_list_region)
        try:
            return read_name(frame)
        except OCRUnavailable as exc:
            self.warn_once(f"OCR indisponível: {exc}")
            return ""

    def creature_present(self) -> bool:
        if self.is_battle_list_empty():
            return False
        text = self.read_battle_list_text()
        return creature_name_present(text, self.creature_name, self.name_match_threshold)

    def press_attack_key(self, dry_run: bool = False) -> None:
        if dry_run:
            self.log(f"[dry-run] pressionaria a tecla de ataque '{self.attack_key}'")
            return
        self.mouse.press_key(self.attack_key)

    def _read_mana(self) -> int | None:
        frame = self.capture.grab(self.config.get("mana_region"))
        return read_number(frame)

    def _maybe_cast_spell(self) -> None:
        if time.monotonic() < self._next_spell_at:
            return
        try:
            if self.check_mana:
                mana = self._read_mana()
                self.emit("mana_reading", mana)
                if mana is None:
                    self.warn_once("Não consegui ler a mana via OCR. Verifique a região configurada.")
                    return
                if mana < int(self.config.get("min_mana", 300)):
                    self.warn_once(f"Mana insuficiente ({mana}) para conjurar - aguardando regenerar...")
                    return
        except OCRUnavailable as exc:
            self.warn_once(f"ERRO de OCR (magia de ataque): {exc}")
            return

        if not self.request_floor(timeout=5.0):
            return
        try:
            self.mouse.press_key(self.spell_hotkey)
        finally:
            self.release_floor()
        self.log(f"Magia de ataque conjurada (tecla {self.spell_hotkey}).")
        self._next_spell_at = time.monotonic() + InputSimulator.random_delay(
            self.config.get("spell_delay_min", 1.5), self.config.get("spell_delay_max", 2.5)
        )

    def loop(self) -> None:
        while not self.stopped:
            if not self.wait_for_higher_priority():
                return
            self.maybe_send_anti_afk()
            self._emit_elapsed()

            if not self.creature_present():
                self._missing_count += 1
                if self._missing_count == 1:
                    self.log(f"Alvo de treino '{self.creature_name}' não encontrado na lista - tentando de novo...")
                if self._missing_count >= self.missing_retries:
                    self.log("Alvo de treino não encontrado - verifique se ainda está por perto.")
                    self.warn_popup("Alvo de treino não encontrado - verifique se ainda está por perto.")
                    self.pause()
                    self._missing_count = 0
                    continue
                if not self.sleep(self.missing_retry_interval):
                    return
                continue

            self._missing_count = 0

            if not self.is_attacking():
                if not self.request_floor(timeout=5.0):
                    if not self.sleep(1.0):
                        return
                    continue
                try:
                    self.press_attack_key()
                finally:
                    self.release_floor()

                if not self.sleep(self.attack_check_delay):
                    return
                attacking = self.is_attacking()
                self.bump_counter()
                self.log(
                    f"Ataque #{self.counter}: tecla '{self.attack_key}' pressionada - "
                    f"atacando={'sim' if attacking else 'não confirmado'}."
                )

            if self.cast_spell_enabled:
                self._maybe_cast_spell()

            while not self.stopped:
                if not self.wait_for_higher_priority():
                    return
                if not self.sleep(InputSimulator.random_delay(
                    self.config.get("engaged_delay_min", 1.0), self.config.get("engaged_delay_max", 2.0)
                )):
                    return
                self.maybe_send_anti_afk()
                self._emit_elapsed()
                if not self.creature_present():
                    break
                if self.cast_spell_enabled:
                    self._maybe_cast_spell()
                if not self.is_attacking():
                    break
