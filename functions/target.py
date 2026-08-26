"""Target - le a Battle List do client e ataca a primeira criatura valida.

A Battle List do proprio Tibia ja identifica e ordena as criaturas visiveis
(por Health/Distance/Age/Name, ASC/DESC - configurado pelo usuario dentro do
jogo). Reconhecer sprites soltos no mapa seria muito mais fragil; em vez
disso este modulo so LE a lista, linha por linha, de cima para baixo, na
ordem em que ela ja esta - sem reimplementar nenhuma ordenacao.

Cada ciclo:
    1. captura a regiao da Battle List inteira (mss)
    2. divide em N "slots" de linha (altura fixa, calibrada pelo usuario)
    3. por slot: ocupado/vazio (template matching, mesmo padrao do RuneMaker),
       nome da criatura (OCR, Tesseract) e estado de selecao (borda vermelha
       = "attack", verde = "follow", nenhuma = nao selecionado - por amostra
       de cor HSV, calibrada pelo usuario)
    4. se ja ha um alvo selecionado e ele continua na lista, nao faz nada
       (evita re-clicar a toa); se sumiu (morreu) ou nunca havia alvo,
       escolhe a primeira linha ocupada que passa no filtro de
       whitelist/blacklist e dispara a acao de ataque configurada

Tudo baseado em pixels da tela + input simulado. Nenhuma leitura de memoria.

Fora de escopo nesta versao (ver README/prompt original) - so mencionado
aqui como proxima extensao possivel:
    - leitura de vida/mana do proprio personagem (fugir/usar pocao)
    - movimentacao ate o alvo (assume fight/chase mode ja configurado no jogo)
    - loot automatico apos a morte da criatura
    - priorizacao de alvo por vida (o campo `life_pct` ja e lido e exposto no
      log de teste, mas a escolha de alvo aqui e so "primeira linha valida").
"""

from __future__ import annotations

import difflib
import time
from dataclasses import dataclass

import cv2
import numpy as np

from core.input_simulator import InputSimulator
from core.screen_capture import ScreenCapture, is_valid_region, load_image
from core.worker import BaseWorker
from functions.rune_maker import OCRUnavailable, configure_tesseract

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None


NAME_OCR_CONFIG = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz' "


def preprocess_name_for_ocr(frame: np.ndarray) -> np.ndarray:
    """Pre-processamento proprio pro nome da Battle List - diferente do
    `preprocess_for_ocr` do RuneMaker (luminancia ponderada, feito pra texto
    branco simples de mana/quantidade), aqui o nome muda de COR conforme o
    estado de selecao (branco=normal, vermelho=attack, verde=follow...).

    Luminancia ponderada da pouco peso ao canal R (~0.3x) - texto vermelho
    fica com brilho luminancia proximo do fundo escuro do painel, e o
    threshold de Otsu perde o texto (medido: contraste de ~34 contra ~190 do
    texto branco). Usar o MAXIMO entre os canais B/G/R em vez da luminancia
    trata qualquer cor saturada (branco ou vermelho) como "clara" contra o
    fundo escuro, dando um contraste forte (~160) em ambos os casos.
    """
    bright = np.max(frame, axis=2).astype(np.uint8)
    bright = cv2.resize(bright, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    bright = cv2.medianBlur(bright, 3)
    _, binary = cv2.threshold(bright, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(binary) < 127:
        binary = cv2.bitwise_not(binary)
    return binary


# --------------------------------------------------------------------------
# Leitura/parsing
# --------------------------------------------------------------------------
@dataclass
class BattleListRow:
    index: int
    occupied: bool
    name: str | None = None
    selection: str = "none"  # "none" | "follow" | "attack"
    life_pct: int | None = None  # exposto so no log de teste (ver docstring do modulo)


def read_name(frame: np.ndarray) -> str:
    """Le o nome da criatura no recorte (faixa de texto da linha). String
    vazia se o Tesseract nao reconhecer nada."""
    if pytesseract is None:
        raise OCRUnavailable(
            "pytesseract nao instalado. Instale-o e o Tesseract OCR."
        )
    processed = preprocess_name_for_ocr(frame)
    try:
        text = pytesseract.image_to_string(processed, config=NAME_OCR_CONFIG)
    except Exception as exc:  # binario do Tesseract ausente
        raise OCRUnavailable(f"Falha ao executar o Tesseract: {exc}") from exc
    return " ".join(text.split())


def row_region(battle_list_region, row_height: int, index: int) -> list[int]:
    x, y, w, _h = battle_list_region
    return [int(x), int(y + index * row_height), int(w), int(row_height)]


def row_count_for(battle_list_region, row_height: int) -> int:
    if not battle_list_region or not row_height:
        return 0
    return max(0, int(battle_list_region[3]) // int(row_height))


def crop_offset(frame: np.ndarray, offset) -> np.ndarray | None:
    """`offset` = [dx, dy, w, h] relativo ao topo-esquerda de `frame`.
    Devolve o recorte, ou None se cair fora dos limites do frame."""
    if not offset:
        return None
    dx, dy, w, h = (int(v) for v in offset)
    fh, fw = frame.shape[:2]
    x0, y0 = max(0, dx), max(0, dy)
    x1, y1 = min(fw, dx + w), min(fh, dy + h)
    if x1 <= x0 or y1 <= y0:
        return None
    return frame[y0:y1, x0:x1]


def row_is_empty(frame_row: np.ndarray, empty_template: np.ndarray | None, threshold: float = 0.90) -> bool | None:
    """Mesmo padrao de deteccao de slot vazio do RuneMaker
    (`functions.rune_maker.slot_is_empty`): template matching, nao
    heuristica de cor. None = sem template calibrado (chamador decide)."""
    if empty_template is None or frame_row.size == 0:
        return None
    template = empty_template
    if frame_row.shape[:2] != template.shape[:2]:
        template = cv2.resize(template, (frame_row.shape[1], frame_row.shape[0]))
    result = cv2.matchTemplate(frame_row, template, cv2.TM_CCOEFF_NORMED)
    result = np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)
    return float(result.max()) >= threshold


def _text_foreground_mask(crop: np.ndarray, brightness_cutoff: int = 100) -> np.ndarray:
    """Mascara dos pixels de TEXTO dentro de um recorte (fundo escuro do
    painel a parte) - mesma ideia do canal maximo B/G/R usado no
    pre-processamento de OCR (`preprocess_name_for_ocr`): qualquer cor
    saturada (branco ou vermelho/verde do nome) conta como "texto",
    independente da luminancia ponderada."""
    return np.max(crop, axis=2) > brightness_cutoff


def sample_name_text_color(frame: np.ndarray, tolerance: tuple[int, int, int] = (10, 60, 60)):
    """Deriva uma faixa HSV a partir da COR DO TEXTO (nao do recorte
    inteiro) - alguns clients de Tibia indicam selecao mudando a cor do
    NOME da criatura (vermelho=attack, verde=follow), sem nenhuma borda
    separada. Usar so os pixels de texto (via `_text_foreground_mask`) evita
    que o fundo escuro (a maior parte da area do recorte) domine a mediana,
    o que aconteceria usando o recorte inteiro (como o `sample_hsv_range` do
    AutoFishing faz, pensado pra um recorte de cor uniforme tipo agua)."""
    mask = _text_foreground_mask(frame)
    pixels = frame[mask] if np.any(mask) else frame.reshape(-1, 3)
    hsv_pixels = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    median = np.median(hsv_pixels, axis=0)
    th, ts, tv = tolerance
    lower = [
        int(max(0, median[0] - th)),
        int(max(0, median[1] - ts)),
        int(max(0, median[2] - tv)),
    ]
    upper = [
        int(min(179, median[0] + th)),
        int(min(255, median[1] + ts)),
        int(min(255, median[2] + tv)),
    ]
    return lower, upper


def classify_name_color(
    crop: np.ndarray | None,
    attack_range: tuple[list[int], list[int]] | None,
    follow_range: tuple[list[int], list[int]] | None,
    min_coverage: float = 0.15,
) -> str:
    """Classifica "attack"/"follow"/"none" pela cor do proprio TEXTO do nome
    (mesmo recorte usado pro OCR) - alguns clients (confirmado neste projeto)
    nao desenham nenhuma borda de selecao separada, so mudam a cor do nome.
    So considera os pixels de TEXTO (via `_text_foreground_mask`), nao o
    recorte inteiro, senao o fundo escuro (a maior parte da area) dilui a
    fracao e nada bate o `min_coverage`."""
    if crop is None or crop.size == 0:
        return "none"
    mask = _text_foreground_mask(crop)
    total_fg = int(np.count_nonzero(mask))
    if total_fg == 0:
        return "none"
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

    def coverage(hsv_range) -> float:
        if not hsv_range:
            return 0.0
        lower, upper = hsv_range
        color_mask = cv2.inRange(hsv, np.array(lower, dtype=np.uint8), np.array(upper, dtype=np.uint8))
        return int(np.count_nonzero((color_mask > 0) & mask)) / total_fg

    red_cov = coverage(attack_range)
    green_cov = coverage(follow_range)
    if red_cov >= min_coverage and red_cov >= green_cov:
        return "attack"
    if green_cov >= min_coverage:
        return "follow"
    return "none"


def read_life_percentage(frame_row: np.ndarray, offset) -> int | None:
    """Heuristica generica de mini barra de vida: fracao (da esquerda pra
    direita) de colunas "preenchidas" (brilho acima do fundo escuro/vazio da
    barra), independente da cor especifica (verde/amarelo/laranja/vermelho
    mudam conforme a vida cai, mas o trecho vazio e sempre bem mais escuro).

    So usado no log de "Testar leitura" nesta versao - ver docstring do
    modulo (extensao futura: priorizacao de alvo por vida)."""
    crop = crop_offset(frame_row, offset)
    if crop is None or crop.size == 0:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    column_brightness = gray.mean(axis=0)
    filled_cols = int(np.sum(column_brightness > 60))
    return int(round(100 * filled_cols / max(1, gray.shape[1])))


# --------------------------------------------------------------------------
# Filtro de nomes (whitelist/blacklist)
# --------------------------------------------------------------------------
def normalize_name(name: str | None) -> str:
    return " ".join((name or "").strip().split()).lower()


def name_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def name_passes_filter(name: str | None, creature_list: list[str], mode: str, threshold: float = 0.80) -> bool:
    """Tolerante a pequenas falhas de OCR (comparacao por similaridade, nao
    igualdade exata) - "whitelist" so aceita nomes que baterem com a lista;
    "blacklist" aceita qualquer nome, exceto os que baterem."""
    norm_name = normalize_name(name)
    if not norm_name:
        return False
    norm_list = [normalize_name(n) for n in creature_list if normalize_name(n)]
    matched = any(name_similarity(norm_name, entry) >= threshold for entry in norm_list)
    return matched if mode == "whitelist" else not matched


# --------------------------------------------------------------------------
# Worker
# --------------------------------------------------------------------------
class TargetWorker(BaseWorker):
    name_label = "target"

    def setup(self) -> None:
        self.capture = ScreenCapture()
        self.mouse = InputSimulator(
            background_hwnd=self.config.get("_background_hwnd"),
            on_fallback=self.log,
        )
        self.register_with_coordinator("target")

        self.battle_list_region = self.config.get("battle_list_region")
        if not is_valid_region(self.battle_list_region):
            raise ValueError("Regiao da Battle List nao configurada.")

        self.row_height = int(self.config.get("row_height") or 0)
        if self.row_height <= 0:
            raise ValueError("Altura de linha nao calibrada.")

        self.row_count = row_count_for(self.battle_list_region, self.row_height)
        if self.row_count <= 0:
            raise ValueError("Regiao da Battle List menor que uma linha - recalibre.")

        self.empty_template = self._load_template("row_empty_template")
        if self.empty_template is None:
            raise ValueError("Template de linha vazia nao calibrado.")
        self.empty_threshold = float(self.config.get("empty_match_threshold", 0.90))

        self.name_crop_offset = self.config.get("name_crop_offset")
        if not self.name_crop_offset:
            self.log(
                "AVISO: faixa de texto do nome nao calibrada - o filtro de "
                "whitelist/blacklist nao vai reconhecer nomes."
            )

        self.attack_range = self._hsv_range("attack_name_hsv_lower", "attack_name_hsv_upper")
        self.follow_range = self._hsv_range("follow_name_hsv_lower", "follow_name_hsv_upper")
        if not self.attack_range and not self.follow_range:
            self.log(
                "AVISO: cor do nome em attack/follow nao calibrada - o Target "
                "vai reforcar a acao de ataque a cada ciclo, mesmo ja selecionado."
            )

        self.life_bar_offset = self.config.get("life_bar_offset")

        self.attack_mode = self.config.get("attack_mode", "single_click")
        self.context_menu_offset = self.config.get("context_menu_offset") or [0, 0]

        self.filter_mode = self.config.get("filter_mode", "blacklist")
        self.creature_list = [str(n) for n in (self.config.get("creature_list") or [])]
        self.name_match_threshold = float(self.config.get("name_match_threshold", 0.80))

        configure_tesseract(on_progress=self.log)

        self._last_warning = ""

        self.log(
            f"Target iniciado (linhas={self.row_count}, modo_ataque={self.attack_mode}, "
            f"filtro={self.filter_mode}, backend={InputSimulator.backend_name()})."
        )

    def teardown(self) -> None:
        capture = getattr(self, "capture", None)
        if capture is not None:
            capture.close()
        self.unregister_from_coordinator()
        self.log(f"Target finalizado. Alvos atacados na sessao: {self.counter}.")

    # ------------------------------------------------------------- calibracao
    def _load_template(self, key: str):
        path = self.config.get(key)
        if not path:
            return None
        try:
            return load_image(path)
        except Exception:
            return None

    def _hsv_range(self, lower_key: str, upper_key: str):
        lower = self.config.get(lower_key)
        upper = self.config.get(upper_key)
        if not lower or not upper:
            return None
        return (lower, upper)

    def warn_once(self, message: str) -> None:
        if message != self._last_warning:
            self.log(message)
            self._last_warning = message

    # ------------------------------------------------------------- leitura
    def read_rows(self, frame: np.ndarray) -> list[BattleListRow]:
        """`frame` e o recorte inteiro da regiao da Battle List."""
        rows: list[BattleListRow] = []
        for i in range(self.row_count):
            y0 = i * self.row_height
            y1 = y0 + self.row_height
            row_frame = frame[y0:y1, :]
            if row_frame.size == 0:
                continue

            empty = row_is_empty(row_frame, self.empty_template, self.empty_threshold)
            if empty:
                rows.append(BattleListRow(index=i, occupied=False))
                continue

            name = None
            selection = "none"
            if self.name_crop_offset:
                crop = crop_offset(row_frame, self.name_crop_offset)
                if crop is not None and crop.size > 0:
                    try:
                        name = read_name(crop)
                    except OCRUnavailable as exc:
                        self.warn_once(f"OCR indisponivel: {exc}")
                    # mesmo recorte do nome: alguns clients (confirmado neste
                    # projeto) indicam selecao mudando so a COR do texto do
                    # nome, sem nenhuma borda separada pra calibrar.
                    selection = classify_name_color(crop, self.attack_range, self.follow_range)

            life_pct = read_life_percentage(row_frame, self.life_bar_offset) if self.life_bar_offset else None

            rows.append(BattleListRow(index=i, occupied=True, name=name, selection=selection, life_pct=life_pct))
        return rows

    def pick_target(self, rows: list[BattleListRow]) -> BattleListRow | None:
        for row in rows:
            if not row.occupied:
                continue
            if name_passes_filter(row.name, self.creature_list, self.filter_mode, self.name_match_threshold):
                return row
        return None

    # ------------------------------------------------------------------ acao
    def _row_center(self, index: int) -> tuple[int, int]:
        x, y, w, _h = self.battle_list_region
        cy = int(y + index * self.row_height + self.row_height / 2)
        cx = int(x + w / 2)
        return cx, cy

    def attack(self, index: int, dry_run: bool = False) -> None:
        cx, cy = self._row_center(index)
        jitter = int(self.config.get("click_jitter", 2))

        if dry_run:
            self.log(f"[dry-run] acao de ataque ({self.attack_mode}) na linha {index} em ({cx}, {cy})")
            return

        # No modo mouse real, o cursor fica em cima da linha depois do
        # clique - alguns clients mudam a cor do nome sob hover (ex: vermelho
        # mais claro que o de "atacando" normal), o que confundiria
        # `classify_name_color` no proximo ciclo. Devolve o cursor pra onde
        # estava ANTES do clique pra nunca deixar hover em cima da lista - em
        # modo background isso e um no-op (o cursor real nunca se move).
        using_real_mouse = self.mouse.is_using_real_mouse()
        origin = InputSimulator.current_position() if using_real_mouse else None

        if self.attack_mode == "double_click":
            self.mouse.double_click(cx, cy, jitter=jitter)
        elif self.attack_mode == "context_menu":
            self.mouse.click(cx, cy, button="right", jitter=jitter)
            time.sleep(InputSimulator.random_delay(0.15, 0.35))
            dx, dy = self.context_menu_offset
            self.mouse.click(cx + int(dx), cy + int(dy), button="left", jitter=0)
        else:
            self.mouse.click(cx, cy, button="left", jitter=jitter)

        if origin is not None:
            self.mouse.move_to(*origin)

    # ------------------------------------------------------------------ ciclo
    def loop(self) -> None:
        while not self.stopped:
            if not self.wait_for_higher_priority():
                return

            frame = self.capture.grab(self.battle_list_region)
            rows = self.read_rows(frame)
            occupied_rows = [r for r in rows if r.occupied]

            if not occupied_rows:
                if not self.sleep(InputSimulator.random_delay(
                    self.config.get("idle_delay_min", 2.0), self.config.get("idle_delay_max", 4.0)
                )):
                    return
                continue

            selected = next((r for r in occupied_rows if r.selection != "none"), None)

            if selected is not None:
                if selected.selection == "follow":
                    if self.request_floor(timeout=5.0):
                        try:
                            self.attack(selected.index)
                        finally:
                            self.release_floor()
                        self.log(f"Alvo '{selected.name or '?'}' em modo follow - reforcando ataque.")
                    elif not self.sleep(1.0):
                        return
                if not self.sleep(InputSimulator.random_delay(
                    self.config.get("delay_min", 0.6), self.config.get("delay_max", 1.4)
                )):
                    return
                continue

            # ninguem selecionado (alvo anterior morreu, ou nenhum ainda escolhido)
            target_row = self.pick_target(occupied_rows)
            if target_row is None:
                if not self.sleep(InputSimulator.random_delay(
                    self.config.get("delay_min", 0.6), self.config.get("delay_max", 1.4)
                )):
                    return
                continue

            if not self.request_floor(timeout=5.0):
                if not self.sleep(1.0):
                    return
                continue
            try:
                self.attack(target_row.index)
            finally:
                self.release_floor()

            self.bump_counter()
            self.log(f"Alvo #{self.counter}: '{target_row.name or '?'}' (linha {target_row.index}).")

            if not self.sleep(InputSimulator.random_delay(
                self.config.get("delay_min", 0.6), self.config.get("delay_max", 1.4)
            )):
                return
