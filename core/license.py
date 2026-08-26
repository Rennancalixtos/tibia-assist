from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

try:
    import win32crypt
except ImportError:
    win32crypt = None

REQUEST_TIMEOUT = 25

_DPAPI_PREFIX = "dpapi:"


def _protect(plaintext: str) -> str:
    if not plaintext:
        return ""
    if win32crypt is None:
        return plaintext
    encrypted = win32crypt.CryptProtectData(
        plaintext.encode("utf-8"), "EasyF license", None, None, None, 0
    )
    return _DPAPI_PREFIX + base64.b64encode(encrypted).decode("ascii")


def _unprotect(value: str) -> str:
    if not value:
        return ""
    if not value.startswith(_DPAPI_PREFIX):
        return value
    if win32crypt is None:
        return ""
    try:
        raw = base64.b64decode(value[len(_DPAPI_PREFIX) :])
        _desc, plain = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
        return plain.decode("utf-8")
    except Exception:
        return ""

_CACHE_SECRET = b"tibia-assist-offline-cache-v1-8f2c1e9a4b6d0731"


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _sign_cache(refresh_token: str, status: str, expires_at: str | None, checked_at: float) -> str:
    payload = "\x00".join(
        [str(refresh_token), str(status), str(expires_at), f"{float(checked_at):.6f}"]
    )
    return hmac.new(_CACHE_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _decode_jwt_claims(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return {}


class LicenseManager:
    def __init__(self, section: dict):
        self.section = section
        self.valid = False
        self.message = "Faca login para ativar o programa."
        self._apply_cached_state()

    @property
    def api_base_url(self) -> str:
        return str(self.section.get("api_base_url") or "").rstrip("/")

    @property
    def grace_period_hours(self) -> float:
        try:
            return float(self.section.get("grace_period_hours", 12))
        except (TypeError, ValueError):
            return 12.0

    @property
    def logged_in(self) -> bool:
        return bool(self.section.get("refresh_token"))

    def _plain(self, key: str) -> str:
        return _unprotect(self.section.get(key, ""))

    @property
    def email(self) -> str:
        token = self._plain("access_token")
        if not token:
            return ""
        return str(_decode_jwt_claims(token).get("email") or "")

    @property
    def expires_label(self) -> str:
        expires = _parse_iso(self.section.get("expires_at"))
        if expires is None:
            return "-"
        delta = expires - datetime.now(timezone.utc)
        total_seconds = delta.total_seconds()
        if total_seconds <= 0:
            return "expirada"
        days = int(total_seconds // 86400)
        hours = int((total_seconds % 86400) // 3600)
        if days > 0:
            return f"{days}d {hours}h"
        minutes = int((total_seconds % 3600) // 60)
        if hours > 0:
            return f"{hours}h {minutes}min"
        return f"{minutes}min"

    def _current_cache_sig(self) -> str:
        return _sign_cache(
            self.section.get("refresh_token", ""),
            self.section.get("status", "unknown"),
            self.section.get("expires_at"),
            float(self.section.get("checked_at") or 0),
        )

    def _apply_cached_state(self) -> None:
        if not self.logged_in:
            self.valid = False
            self.message = "Faca login para ativar o programa."
            return
        if self.section.get("cache_sig") != self._current_cache_sig():
            self.valid = False
            self.message = "Sessao local invalida. Conecte-se a internet para revalidar."
            return
        if self.section.get("status") != "active":
            self.valid = False
            self.message = "Assinatura inativa. Verifique seu pagamento."
            return

        expires = _parse_iso(self.section.get("expires_at"))
        if expires is None:
            self.valid = False
            self.message = "Assinatura sem data de expiracao valida."
            return
        if datetime.now(timezone.utc) >= expires:
            self.valid = False
            self.message = "Assinatura expirada."
            return

        checked_at = float(self.section.get("checked_at") or 0)
        age_hours = (time.time() - checked_at) / 3600.0
        if age_hours <= self.grace_period_hours:
            self.valid = True
            self.message = ""
        else:
            self.valid = False
            self.message = "Nao foi possivel confirmar a assinatura online. Conecte-se a internet."

    def _apply_session(self, body: dict) -> None:
        self.section["access_token"] = _protect(body.get("access_token", ""))
        self.section["refresh_token"] = _protect(body.get("refresh_token", ""))
        self.section["access_token_expires_at"] = body.get("expires_at")
        if "session_token" in body:
            self.section["session_token"] = body.get("session_token") or ""
        license_info = body.get("license") or {}
        self.section["status"] = license_info.get("status", "unknown")
        self.section["expires_at"] = license_info.get("expires_at")
        self.section["checked_at"] = time.time()
        self.section["cache_sig"] = self._current_cache_sig()
        self.valid = bool(license_info.get("valid"))
        self.message = "" if self.valid else str(license_info.get("reason") or "Assinatura invalida.")

    def _clear_session(self) -> None:
        self.section["access_token"] = ""
        self.section["refresh_token"] = ""
        self.section["access_token_expires_at"] = None
        self.section["session_token"] = ""
        self.section["status"] = "unknown"
        self.section["expires_at"] = None
        self.section["cache_sig"] = ""
        self.valid = False

    def _post(self, path: str, payload: dict) -> tuple[int, dict | None]:
        if not self.api_base_url:
            return 0, None
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.api_base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8"))
            except (ValueError, OSError):
                return exc.code, None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return 0, None

    def signup(self, email: str, password: str) -> bool:
        if not self.api_base_url:
            self.message = "Backend de licenca nao configurado (api_base_url vazio)."
            return False
        status, body = self._post("/api/auth/signup", {"email": email, "password": password})
        if body is None:
            self.message = "Sem conexao com o servidor de licenca."
            return False
        if status != 200:
            self.message = str(body.get("error") or "Falha ao cadastrar.")
            return False
        self._apply_session(body)
        return self.valid

    def login(self, email: str, password: str) -> bool:
        if not self.api_base_url:
            self.message = "Backend de licenca nao configurado (api_base_url vazio)."
            return False
        status, body = self._post("/api/auth/login", {"email": email, "password": password})
        if body is None:
            self.message = "Sem conexao com o servidor de licenca."
            return False
        if status != 200:
            self.message = str(body.get("error") or "Credenciais invalidas.")
            return False
        self._apply_session(body)
        return self.valid

    def refresh(self) -> bool:
        refresh_token = self._plain("refresh_token")
        if not refresh_token:
            self.valid = False
            self.message = "Faca login para ativar o programa."
            return False
        if not self.api_base_url:
            self.valid = False
            self.message = "Backend de licenca nao configurado (api_base_url vazio)."
            return False

        status, body = self._post("/api/auth/refresh", {"refresh_token": refresh_token})
        if body is None:
            self._apply_cached_state()
            if not self.valid:
                self.message = (
                    "Sem conexao com o servidor de licenca e sem validacao "
                    "recente em cache. " + self.message
                )
            return self.valid
        if status == 401:
            self._clear_session()
            self.message = str(body.get("error") or "Sessao expirada. Faca login novamente.")
            return False
        if status != 200:
            self._apply_cached_state()
            return self.valid

        self._apply_session(body)
        return self.valid

    def start_checkout(self) -> str | None:
        access_token = self._plain("access_token")
        if not access_token:
            self.message = "Faca login antes de assinar."
            return None
        status, body = self._post("/api/stripe/checkout", {"access_token": access_token})
        if body is None:
            self.message = "Sem conexao com o servidor de licenca."
            return None
        if status != 200:
            self.message = str(body.get("error") or "Nao foi possivel iniciar o pagamento.")
            return None
        return body.get("url")

    def logout(self) -> None:
        access_token = self._plain("access_token")
        if access_token:
            self._post("/api/auth/logout", {"access_token": access_token})
        self._clear_session()
        self.message = "Faca login para ativar o programa."

    def heartbeat(self) -> str:
        session_token = str(self.section.get("session_token") or "")
        if not session_token:
            return "ok"

        access_token = self._plain("access_token")
        if not access_token:
            return "auth_error"

        outcome = self._heartbeat_once(access_token, session_token)
        if outcome != "auth_error":
            return outcome

        if not self.refresh():
            return "auth_error"
        access_token = self._plain("access_token")
        if not access_token:
            return "auth_error"
        return self._heartbeat_once(access_token, session_token)

    def _heartbeat_once(self, access_token: str, session_token: str) -> str:
        status, body = self._post(
            "/api/auth/heartbeat", {"access_token": access_token, "session_token": session_token}
        )
        if body is None:
            return "network_error"
        if status == 401:
            return "auth_error"
        if status != 200:
            return "network_error"
        if body.get("ok"):
            return "ok"
        reason = body.get("reason")
        return "replaced" if reason == "replaced" else "ok"
