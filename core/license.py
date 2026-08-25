"""Cliente de autenticacao/licenca - login por email+senha contra o backend.

Sem uma sessao com assinatura ativa, nenhuma rotina (AutoFishing/RuneMaker)
roda - ver `App.start_worker` em gui/app.py. A sessao (access/refresh token)
fica persistida na secao "license" do config.json (mesmo mecanismo usado
pelas outras abas). Uma janela de tolerancia offline evita bloquear o
usuario por uma falha de rede passageira, mas a expiracao real da
assinatura e sempre decidida pelo backend.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

REQUEST_TIMEOUT = 10

# Segredo fixo embutido no app para assinar o cache local (status/expires_at/
# checked_at) e detectar edicao manual do config.json. NAO e um segredo real
# (esta no binario/fonte, um engenheiro reverso pode extrai-lo) - o objetivo e
# so impedir que editar o JSON num editor de texto burle o periodo de
# tolerancia offline, nao resistir a um ataque dedicado ao binario.
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


class LicenseManager:
    """Guarda a sessao ativa e fala com o backend (Vercel) para valida-la.

    `section` e o dict de `Config.section("license")` - mutado in-place e
    persistido pelo chamador (o mesmo padrao das abas de configuracao).
    """

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

    # --------------------------------------------------------------- estado
    def _current_cache_sig(self) -> str:
        return _sign_cache(
            self.section.get("refresh_token", ""),
            self.section.get("status", "unknown"),
            self.section.get("expires_at"),
            float(self.section.get("checked_at") or 0),
        )

    def _apply_cached_state(self) -> None:
        """Sem internet, aceita o ultimo estado 'active' por algumas horas.

        So confia nesses campos se a assinatura HMAC local ainda bater - do
        contrario, o config.json foi editado manualmente (ou corrompido) e a
        tolerancia offline nao se aplica, forcando uma revalidacao online.
        """
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
        self.section["access_token"] = body.get("access_token", "")
        self.section["refresh_token"] = body.get("refresh_token", "")
        self.section["access_token_expires_at"] = body.get("expires_at")
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
        self.section["status"] = "unknown"
        self.section["expires_at"] = None
        self.section["cache_sig"] = ""
        self.valid = False

    # ------------------------------------------------------------- rede
    def _post(self, path: str, payload: dict) -> tuple[int, dict | None]:
        """POST JSON no backend. Devolve (status_code, body) - body None se
        a requisicao falhou por rede (sem servidor pra responder)."""
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
        """Renova a sessao e revalida a assinatura; sem rede, cai no cache."""
        refresh_token = self.section.get("refresh_token")
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
            # Sem rede: mantem a sessao local e usa a tolerancia offline.
            self._apply_cached_state()
            if not self.valid:
                self.message = (
                    "Sem conexao com o servidor de licenca e sem validacao "
                    "recente em cache. " + self.message
                )
            return self.valid
        if status == 401:
            # Sessao realmente invalidada pelo servidor - precisa logar de novo.
            self._clear_session()
            self.message = str(body.get("error") or "Sessao expirada. Faca login novamente.")
            return False
        if status != 200:
            self._apply_cached_state()
            return self.valid

        self._apply_session(body)
        return self.valid

    def start_checkout(self) -> str | None:
        """Pede ao backend uma URL de checkout do Stripe pra assinatura atual."""
        access_token = self.section.get("access_token")
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
        self._clear_session()
        self.message = "Faca login para ativar o programa."
