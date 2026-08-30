# Prompt de implementação — AutoLoot (SDD)

> Cole este prompt inteiro numa instância nova do Claude Code, aberta na raiz deste mesmo projeto (`tibia-assist`).

## Contexto

Você está trabalhando no `tibia-assist`, um app desktop (PySide6, Windows) de automação/assistência pra Tibia. Leia `CLAUDE.md` primeiro e siga as regras de lá à risca (zero comentários no código, PT-BR com acentuação correta em texto visível ao usuário, nunca tocar widget Qt fora da main thread).

Antes de escrever qualquer código, leia `docs/auto_loot_plano.md` (relatório de viabilidade já feito) - ele mapeia exatamente o que já existe no projeto e pode ser reaproveitado sem alteração. Leia também estes arquivos pra entender os padrões que você vai seguir:

- `functions/cavebot.py` (worker mais parecido em estrutura e recência: config de lista ordenada, `register_with_coordinator`, `wait_for_higher_priority`/`request_floor`/`release_floor` em torno do clique, skip-on-failure em vez de erro fatal)
- `functions/target.py` (função livre `attack_color_present`, e o padrão `_engage()`/`request_floor` cobrindo o combate inteiro)
- `gui/qt/dialogs/module_config/cavebot.py` (tela de config com lista editável add/editar/remover/mover, `InfoIcon` em cada campo não óbvio)
- `gui/qt/dialogs/module_config/target.py` e `fishing.py` (captura de template ao vivo: `select_region` → `ScreenCapture().grab()` → `save_image()`)
- `core/worker.py`, `core/coordinator.py`, `core/input_simulator.py`, `core/background_input.py`, `core/screen_capture.py`

## Objetivo

Implementar o módulo **AutoLoot**: depois que o Target mata um monstro, abrir o corpo automaticamente e recolher os itens configurados pra uma backpack de destino, tudo respeitando a fila de prioridade do `AutomationCoordinator` (não pode atrapalhar nem ser atrapalhado pelas outras rotinas rodando ao mesmo tempo).

## Fluxo funcional (confirmado com o usuário, não inventar variação)

1. Numa região demarcada pelo usuário (`death_watch_region`), monitorar continuamente a presença da mesma cor RGB usada pelo ataque (`attack_color_rgb`/`tolerance`/`min_pixels`, mesmo conceito do Target, mas lido na tela do jogo, não na Battle List).
2. Enquanto a cor estiver presente, guardar a posição absoluta na tela do centro do blob encontrado (`last_seen_xy`).
3. Quando a cor deixar de ser encontrada (transição presente→ausente) e havia uma posição guardada, isso é o sinal de morte: disparar a sequência de loot usando essa posição.
4. Sequência de loot (deve seomar o "chão" - `request_floor` - do início ao fim, num único `try`/`finally`, igual `TargetWorker._engage`/`CavebotWorker._locate_and_click` já fazem):
   a. Clique com botão direito em `last_seen_xy` (abre o corpo). Esperar `open_corpse_delay_s` (cancelável, via `self.sleep`).
   b. Repetir até esgotar `max_loot_passes` ou não achar mais nada: capturar a região `corpse_region`, procurar cada item configurado em `loot_items` (na ordem da lista) via `cv2.matchTemplate`; ao achar um acima da confiança configurada, arrastar (`InputSimulator.drag`, já existe e já suporta modo background) da posição encontrada até `destination_point`; se nada for encontrado nessa passada, parar o loop.
   c. Antes de cada ação dentro do loop, chamar `self.wait_for_higher_priority()` (permite o Target reassumir o chão no meio do loot se aparecer um monstro novo).
5. Depois de terminar (ou desistir), soltar o chão (`release_floor`) e voltar a monitorar `death_watch_region` pro próximo kill.

## Decisão de prioridade já tomada (não é pergunta em aberto)

Em `core/coordinator.py`, mudar:

```python
PRIORITY_ORDER = ["target", "training", "runemaker", "fishing", "auto_food", "cavebot"]
```

para:

```python
PRIORITY_ORDER = ["target", "auto_loot", "training", "runemaker", "fishing", "auto_food", "cavebot"]
```

Motivo (já documentado em `docs/auto_loot_plano.md` §4): o AutoLoot precisa segurar prioridade sobre Training/RuneMaker/Fishing/AutoFood/Cavebot durante o loot, mas o Target precisa poder interromper o AutoLoot a qualquer momento.

## Especificação de dados (config)

Nova seção `config["auto_loot"]`, seguindo a convenção de nomenclatura já usada no projeto (`snake_case`, sufixos `_region`/`_delay_s`/`_enabled` etc):

```python
{
    "death_watch_region": [x, y, w, h],       # region calibrada via select_region
    "corpse_region": [x, y, w, h],            # region calibrada via select_region (bag de origem já aberta)
    "destination_point": [x, y],              # ponto calibrado via select_point (bag de destino)
    "attack_color_rgb": [r, g, b],            # default: copiar de config["target"]["attack_color_rgb"] se existir, senão [254, 0, 0]
    "attack_color_tolerance": 6,
    "attack_color_min_pixels": 3,
    "open_corpse_delay_s": 0.6,
    "check_interval": 0.3,                    # intervalo de polling do death_watch_region
    "loot_scan_timeout_s": 3.0,
    "max_loot_passes": 10,
    "click_jitter": 2,
    "loot_items": [
        {"icon": "<caminho absoluto sob ASSETS_DIR/auto_loot/>", "nome": "<label livre>", "confidence": 0.85}
    ],
}
```

Os ícones de item de loot são capturados pelo próprio usuário (não vêm pré-empacotados como os do Cavebot) - salvar em `ASSETS_DIR/auto_loot/` (criar o diretório se não existir, mesmo padrão de `os.makedirs(ASSETS_DIR, exist_ok=True)` já usado em `target.py`/`fishing.py`).

## Arquivos a criar

### `functions/auto_loot.py`

- Funções livres reaproveitando o padrão de `functions/target.py`:
  - Extrair (ou reaproveitar, se decidir importar de `functions/target.py`) a máscara de cor pra uma função auxiliar comum, e criar `attack_color_centroid(frame, rgb, tolerance, min_pixels) -> tuple[int, int] | None` retornando o centro (x, y) relativo ao frame do maior blob que bate a tolerância, ou `None` se não achar. **Não duplicar a lógica de `cv2.inRange` que já existe em `attack_color_present`** - refatore pra uma função compartilhada que ambas chamam, ou faça `attack_color_centroid` reaproveitar `attack_color_present` internamente pra decidir presença e só then calcular o centróide via `cv2.findNonZero`/`np.mean` na máscara.
- `AutoLootWorker(BaseWorker)`, `name_label = "auto_loot"`:
  - `setup()`: valida `_background_hwnd`, `death_watch_region`, `corpse_region`, `destination_point`, `loot_items` (pelo menos 1 configurado - senão `ValueError` com mensagem clara pro usuário, mesmo padrão de mensagens de erro do Cavebot/Target), carrega os templates de `loot_items` em memória (`load_image`, igual `CavebotWorker.setup` carrega `self.icons`), monta `ScreenCapture`, `InputSimulator`, `register_with_coordinator("auto_loot")`.
  - `teardown()`: fecha capture, `unregister_from_coordinator()`, loga contagem de itens recolhidos na sessão (`self.counter`).
  - `loop()`: laço principal - por tick, capturar `death_watch_region`, chamar `attack_color_centroid`; manter estado `last_seen_xy` e uma flag de "estava presente no tick anterior"; na transição presente→ausente com `last_seen_xy` setado, chamar `self._loot_sequence(last_seen_xy)` e depois zerar `last_seen_xy`. Sempre `self.wait_for_higher_priority()` no início do laço (mesmo padrão de todos os outros workers) e `self.sleep(self.check_interval)` entre ticks (cancelável).
  - `_loot_sequence(xy)`: implementa o passo 4 do fluxo acima. Envolver TUDO em `request_floor(timeout=5.0)`/`try`/`finally: release_floor()`; se `request_floor` falhar, logar e desistir dessa sequência (não travar o worker) - mesmo tratamento do `"floor_denied"` do Cavebot.
  - Ao abrir o corpo: `self.mouse.click(x, y, button="right", jitter=self.click_jitter)`.
  - Ao encontrar um item configurado dentro de `corpse_region`: calcular a posição absoluta do match (origem da região + posição relativa do match, igual `CavebotWorker._locate_and_click` faz a conversão ROI→tela) e `self.mouse.drag(src_x, src_y, dest_x, dest_y, from_jitter=self.click_jitter, to_jitter=self.click_jitter)`.
  - Logar cada evento relevante em PT-BR com acentuação correta (morte detectada, corpo aberto, item recolhido com nome, "nada mais encontrado no corpo", desistência por floor negado) - siga o tom e formato de log já usado em `cavebot.py`/`target.py` (`self.log(f"...")`, com `self.bump_counter()` a cada item recolhido).

### `gui/qt/dialogs/module_config/auto_loot.py`

Espelhar a estrutura de `cavebot.py` (mesmo arquivo é a melhor referência viva no projeto):

- `_ConfigDialog(QDialog)` idêntica (ignora `closeEvent`, só esconde).
- `_AddLootItemDialog(QDialog)`: campos `nome` (QLineEdit), `confidence` (QLineEdit, default 0.85), botão "Capturar ícone..." que chama `controller.select_region(...)` + `ScreenCapture().grab()` + `save_image()` pra `ASSETS_DIR/auto_loot/`, com um `QLabel` mostrando "não capturado" / "Ícone salvo (WxH px)" (mesmo texto dinâmico de `_empty_template_label_text` do Target). Botões OK/Cancel só habilitam OK depois de capturar o ícone e preencher o nome.
- `AutoLootModuleView`:
  - `ModuleCard("AutoLoot", stat_specs=[("counter", "Itens recolhidos:", "0")])`, ligado a `configure_requested`/`start_requested`/`pause_requested`/`stop_requested` igual todos os outros.
  - Dois overlays de região (reaproveitar `ManaOverlay` sem `log_overlay`, só a borda) - um pra `death_watch_region`, outro pra `corpse_region` - mostrados em `on_state` quando `running`/`paused`, escondidos quando não.
  - Diálogo de config com seções: "1. Área de monitoramento da morte" (`select_region` + `InfoIcon` explicando por que essa área existe - cave escura), "2. Cor de ataque" (RGB/tolerância/pixels mínimos, com botão "Copiar do Target" que lê `controller.config_store.section("target").get("attack_color_rgb")` e preenche os campos, já que é o valor mais provável de já estar calibrado), "3. Bag de origem (corpo)" (`select_region`), "4. Bag de destino" (`select_point`), "5. Itens de loot" (lista com add/editar/remover/mover, igual a lista de waypoints do Cavebot), "6. Ritmo e limites" (`open_corpse_delay_s`, `check_interval`, `loot_scan_timeout_s`, `max_loot_passes`, `click_jitter`).
  - `InfoIcon` em cada campo não óbvio, seguindo o padrão de quebra de linha já corrigido em `gui/qt/components/info_tooltip.py` (`\n` vira `<br><br>` automaticamente - é só usar `\n` entre parágrafos ao escrever o texto).
  - `start()`: valida as três regiões/ponto + pelo menos 1 item de loot configurado antes de chamar `controller.start_worker`.

### Wiring

- `gui/qt/pages/dashboard.py`: importar `AutoLootModuleView`, instanciar (`self.auto_loot_view = AutoLootModuleView(controller, main_window)`) junto dos outros, mesma linha de padrão de `fishing_view`/`runemaker_view`/etc.
- `core/coordinator.py`: `PRIORITY_ORDER` atualizado (ver seção acima).
- `gui/qt/pages/settings.py`: no texto do `WarningBanner` de `_build_background_box`, incluir "AutoLoot" na lista de módulos que usam o mouse (`AutoFood, AutoFishing, Cavebot, RuneMaker` → adicionar `AutoLoot`).

## Fora de escopo (não implementar nesta versão, documentado em `docs/auto_loot_plano.md` §5)

- Múltiplos corpos simultâneos.
- Calibração automática de `corpse_region` (é sempre manual).
- OCR de nome de item.
- Diálogo de quantidade do Tibia pra itens empilháveis.
- Ordenação/priorização de valor dos itens além da ordem da lista configurada.

## Critérios de aceite

- `python -m py_compile` limpo em todos os arquivos novos/alterados.
- App abre sem erro com o módulo AutoLoot ainda não configurado (deve dar erro claro só ao tentar iniciar, não travar a tela).
- Com Target + AutoLoot rodando juntos: matar um monstro dispara a abertura do corpo e o recolhimento dos itens configurados, sem o Cavebot andar nem o AutoFood/RuneMaker clicarem durante a sequência.
- Se um monstro novo aparecer no meio do loot (Target pede o chão), o AutoLoot pausa e retoma depois, sem perder a sequência atual de forma inconsistente (documentar no log o que aconteceu).
- Nenhum comentário `#`/docstring adicionado ao código novo. Todo texto visível ao usuário (labels, tooltips, mensagens de log/erro) em PT-BR com acentuação correta.

## Observação final

Depois de implementar, siga o fluxo já estabelecido neste projeto: relançar o app (`python main.py`) pra teste manual ao vivo, e passar o diff por uma revisão (`code-reviewer`) antes de considerar pronto - thread-safety entre o novo worker e a UI, e recursos (capture/overlays) sempre liberados no `teardown()`.
