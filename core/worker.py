from __future__ import annotations

import queue
import threading
import time
from datetime import datetime


class BaseWorker(threading.Thread):
    name_label = "worker"

    def __init__(self, config: dict, events: "queue.Queue[tuple]"):
        super().__init__(daemon=True)
        self.config = dict(config)
        self.events = events
        self._stop_event = threading.Event()
        self._resume_event = threading.Event()
        self._resume_event.set()
        self.counter = 0
        self.coordinator = None
        self._coordinator_name: str | None = None

    def stop(self) -> None:
        self._stop_event.set()
        self._resume_event.set()

    def pause(self) -> None:
        self._resume_event.clear()
        self.emit("state", "paused")
        self.log("Pausado.")

    def resume(self) -> None:
        self._resume_event.set()
        self.emit("state", "running")
        self.log("Retomado.")

    def toggle_pause(self) -> None:
        if self.is_paused:
            self.resume()
        else:
            self.pause()

    @property
    def is_paused(self) -> bool:
        return not self._resume_event.is_set()

    @property
    def stopped(self) -> bool:
        return self._stop_event.is_set()

    def emit(self, kind: str, payload=None) -> None:
        self.events.put((self.name_label, kind, payload))

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.emit("log", f"[{stamp}] {message}")

    def emit_config_update(self, updates: dict) -> None:
        self.emit("config_update", updates)

    def warn_popup(self, message: str) -> None:
        self.emit("popup", message)

    def bump_counter(self, amount: int = 1) -> None:
        self.counter += amount
        self.emit("counter", self.counter)

    def sleep(self, seconds: float) -> bool:
        deadline = time.monotonic() + max(0.0, float(seconds))
        while time.monotonic() < deadline:
            if self.stopped:
                return False
            time.sleep(min(0.05, deadline - time.monotonic()))
        return not self.stopped

    def wait_while_paused(self) -> bool:
        while not self._resume_event.wait(timeout=0.1):
            if self.stopped:
                return False
        return not self.stopped

    def register_with_coordinator(self, name: str) -> None:
        self.coordinator = self.config.get("_coordinator")
        self._coordinator_name = name
        if self.coordinator:
            self.coordinator.started(name)

    def unregister_from_coordinator(self) -> None:
        if self.coordinator and self._coordinator_name:
            self.coordinator.stopped(self._coordinator_name)

    def wait_for_higher_priority(self) -> bool:
        name = self._coordinator_name
        externally_paused_logged = False
        while not self.stopped and (
            self.is_paused or (self.coordinator and name and self.coordinator.should_pause(name))
        ):
            if self.coordinator and name and self.coordinator.should_pause(name):
                if not externally_paused_logged:
                    self.log("Pausado (outra rotina está agindo)...")
                    externally_paused_logged = True
                self.coordinator.confirm_paused(name)
            if not self.sleep(0.1):
                return False
        if externally_paused_logged:
            self.log("Retomado.")
        return not self.stopped

    def request_floor(self, timeout: float = 5.0) -> bool:
        if not self.coordinator or not self._coordinator_name:
            return True
        return self.coordinator.request_floor(self._coordinator_name, timeout=timeout)

    def release_floor(self) -> None:
        if self.coordinator and self._coordinator_name:
            self.coordinator.release_floor(self._coordinator_name)

    def run(self) -> None:
        self.emit("state", "running")
        try:
            self.setup()
            self.loop()
        except Exception as exc:
            self.log(f"ERRO: {exc}")
            self.emit("state", "error")
        finally:
            self.teardown()
            self.emit("state", "stopped")

    def setup(self) -> None:
        pass

    def loop(self) -> None:
        raise NotImplementedError

    def teardown(self) -> None:
        pass
