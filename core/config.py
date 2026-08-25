"""Persistencia de configuracoes em JSON.

Todas as configuracoes ficam num unico `config.json` ao lado do `main.py`.
O arquivo e criado na primeira execucao a partir de DEFAULTS e, sempre que
carregado, e mesclado com DEFAULTS para que novas chaves adicionadas em
versoes futuras nao quebrem configuracoes antigas.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from typing import Any


def _base_dir() -> str:
    """Pasta onde o config.json e os assets do usuario devem ficar.

    Rodando pelo fonte: a raiz do projeto (facilita debug/dev).
    Empacotado com PyInstaller: `%APPDATA%\\EasyF` - o padrao do Windows pra
    dados de usuario. Nunca a pasta do .exe (pode estar em Program Files sem
    permissao de escrita, e o auto-update sobrescreve o .exe naquele lugar)
    nem `sys._MEIPASS` (pasta temporaria apagada ao fechar o programa).
    """
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(appdata, "EasyF")
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = _base_dir()
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

DEFAULTS: dict[str, Any] = {
    # Licenca/assinatura - sem uma key valida nenhuma rotina roda.
    "license": {
        # URL base do backend (Vercel) que valida a licenca/checa update.
        "api_base_url": "https://tibia-assist.vercel.app",
        # Tolerancia offline: aceita a ultima validacao "active" por N horas
        # sem internet antes de bloquear as rotinas.
        "grace_period_hours": 12,
        # Intervalo entre revalidacoes automaticas enquanto o programa esta aberto.
        "check_interval_minutes": 30,
        # Sessao e estado da ultima validacao (preenchidos automaticamente, nao editar).
        "access_token": "",
        "refresh_token": "",
        "access_token_expires_at": None,
        # Token de sessao unica por conta (comparado pelo heartbeat periodico
        # com o servidor - ver LicenseManager.heartbeat). "" = conta sem
        # fiscalizacao ainda (nunca logou depois desta feature existir).
        "session_token": "",
        "status": "unknown",
        "expires_at": None,
        "checked_at": 0,
        # Assinatura HMAC dos campos acima (detecta edicao manual do arquivo).
        "cache_sig": "",
    },
    # Hotkeys globais, compartilhadas pelas duas funcoes
    "hotkeys": {
        "pause": "f6",   # pausa / retoma a funcao em execucao
        "stop": "f7",    # para completamente
        "enabled": True,  # permite desligar o hook global de teclado
    },
    "fishing": {
        # Coordenada absoluta [x, y] do slot da vara de pescar na backpack
        "rod_slot": None,
        # Regiao monitorada na tela: [x, y, largura, altura] (coordenadas absolutas)
        "region": None,
        # "hsv" (deteccao por cor) ou "template" (cv2.matchTemplate)
        "detection_mode": "hsv",
        # Faixa HSV da agua - calibravel pelo usuario a partir de um print da tela dele
        "hsv_lower": [90, 60, 40],
        "hsv_upper": [130, 255, 255],
        # Brilho (mediana do V) no momento da calibracao - baseline pro
        # ajuste dinamico dia/noite. None = nunca calibrado, ajuste desligado.
        "hsv_reference_brightness": None,
        # Recalibracao periodica por EMA (opt-in) - o ajuste continuo de V
        # por ciclo (dia/noite) NAO e opt-in, e sempre ativo quando ha
        # hsv_reference_brightness calibrado.
        "auto_recalibrate_enabled": False,
        "auto_recalibrate_interval_minutes": 15,
        "ema_alpha": 0.15,
        # Area minima (em pixels) de agua na regiao para considerar que ha algo a pescar
        "min_area": 200,
        # Tamanho do grid de SQM em pixels (32 = tile padrao do Tibia sem zoom)
        "tile_size": 32,
        # Cobertura minima de agua (0.0 a 1.0) dentro de um SQM para considera-lo valido
        "min_tile_coverage": 0.35,
        # Template salvo em assets/ (usado quando detection_mode == "template")
        "template_file": "water_template.png",
        "template_threshold": 0.80,
        # Clique usado para aplicar a vara (ja aberta com o botao direito) na agua
        "mouse_button": "left",
        # Intervalo aleatorio entre um lance e outro (segundos)
        "delay_min": 1.8,
        "delay_max": 3.2,
        # Variacao aleatoria em pixels aplicada ao ponto clicado (+/-)
        "click_jitter": 2,
        # Sorteia entre os tiles de agua encontrados em vez de usar sempre o primeiro
        "randomize_target": True,
        # Limite opcional de lances na sessao (0 = ilimitado)
        "max_casts": 0,
        # Pausas periodicas para simular descanso humano
        "break_enabled": True,
        # Pesca por um tempo aleatorio de ate 5 min antes de cada pausa
        "break_interval_min": 30,
        "break_interval_max": 300,
        # Cada pausa dura um periodo aleatorio de ate 2 min
        "break_duration_min": 10,
        "break_duration_max": 120,
    },
    # Modo de clique/tecla em background (PostMessage direto pra janela do
    # jogo, sem mover o cursor real). Global (nao e por aba) porque afeta as
    # duas automacoes igual.
    "background_mode": {
        "enabled": False,
        # Substring do titulo da janela do jogo, resolvida de novo (via
        # find_window_by_title) a cada inicio de rotina - nao guardamos o
        # hwnd em si porque ele muda a cada vez que o jogo e reaberto.
        "window_title": "",
    },
    "runemaker": {
        # Tecla de atalho da magia de criar runa configurada dentro do jogo
        "spell_hotkey": "f2",
        # Coordenada absoluta [x, y] do slot de blank runes na backpack
        "blank_slot": None,
        # Quantidade a criar (0 = criar ate acabar mana ou ate o usuario parar)
        "amount": 0,
        # Regiao de OCR: [x, y, largura, altura]
        "mana_region": None,
        # Limite de seguranca: abaixo disso o ciclo pausa sozinho
        "min_mana": 300,
        # Permite rodar sem OCR (usuario assume o controle do limite)
        "check_mana": True,
        # Intervalo aleatorio entre criacoes (segundos) - respeitar o cooldown real
        "delay_min": 1.5,
        "delay_max": 2.5,
        "click_jitter": 2,
        # Caminho do executavel do Tesseract (deixe vazio se estiver no PATH)
        "tesseract_cmd": "",
        # "craft" (cria runas) ou "mana_training" (so conjura, sem item) -
        # mutuamente exclusivos, mesma thread/slot de execucao.
        "mode": "craft",
        # Alguns OTservers aplicam a magia direto no slot da blank rune, sem
        # precisar levar pra mao - quando True, pula todo o manuseio de item.
        "no_hand_mode": False,
        # Coordenadas [x, y] dos slots de mao e de destino (so usados no modo
        # completo, com manuseio de mao)
        "hand_slot": None,
        "output_slot": None,
        # Regioes [x, y, largura, altura] usadas pra comparar cada slot com o
        # template de "vazio" calibrado (ver os campos *_empty_template)
        "blank_slot_region": None,
        "hand_slot_region": None,
        "output_slot_region": None,
        # Caminho do recorte de referencia de cada slot vazio (assets/*.png)
        "blank_empty_template": "",
        "hand_empty_template": "",
        "output_empty_template": "",
        # Confianca minima do template match pra considerar um slot vazio
        "empty_match_threshold": 0.90,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Mescla `override` sobre uma copia de `base`, recursivamente."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """Acesso simples as configuracoes, com chaves em notacao de ponto."""

    def __init__(self, path: str = CONFIG_PATH):
        self.path = path
        self.data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            self.save()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fp:
                stored = json.load(fp)
            self.data = _deep_merge(DEFAULTS, stored)
        except (json.JSONDecodeError, OSError):
            # Arquivo corrompido: mantem os defaults em memoria e preserva o
            # arquivo antigo para inspecao do usuario.
            try:
                os.replace(self.path, self.path + ".bak")
            except OSError:
                pass
            self.data = copy.deepcopy(DEFAULTS)
            self.save()

    def save(self) -> None:
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fp:
            json.dump(self.data, fp, indent=2, ensure_ascii=False)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted_key: str, value: Any) -> None:
        parts = dotted_key.split(".")
        node = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def section(self, name: str) -> dict[str, Any]:
        return self.data.setdefault(name, {})

    def asset_path(self, filename: str) -> str:
        return os.path.join(ASSETS_DIR, filename)
