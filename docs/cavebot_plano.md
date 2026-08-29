# Cavebot — Relatório de Viabilidade e Plano de Implementação

Documento de referência antes de qualquer implementação. Sem código nesta etapa.

## 0. Como capturar um ícone de waypoint (padrão validado em produção)

Aprendido durante os primeiros testes reais: **nunca** gere o template de um ícone a partir da legenda/menu de seleção de marcadores do Tibia (`img/map/iconsmapa.png`) nem de um print do menu de seleção — eles renderizam o ícone numa escala bem maior (~17x22px na legenda, ~55x55px num print do menu) do que o marcador real desenhado no mini mapa (~11x11px). `cv2.matchTemplate` não é invariante a escala, então esse descasamento faz a busca nunca encontrar nada.

Processo que funciona (repita pra cada ícone novo/que falhar):
1. Coloque o marcador de verdade no mini mapa, de preferência já no local real do ponto da rota (ou pelo menos numa área do mapa visível).
2. Tire (ou peça pra eu tirar via PowerShell, se o jogo estiver em primeiro plano) um print mostrando o marcador nesse local.
3. Recorte apertado ao redor do marcador com ~3px de margem.
4. Remova o fundo com flood-fill "magic wand" a partir dos 4 cantos do recorte, **sempre** com a flag `cv2.FLOODFILL_FIXED_RANGE` (`flags=4 | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE`). Sem essa flag, o flood fill compara cada pixel novo com o vizinho já preenchido (faixa "flutuante") em vez da cor original da semente, e vaza progressivamente pra dentro do ícone em gradientes - isso destruiu 3 dos primeiros 7 ícones extraídos antes de adicionar a flag.
5. Salve como RGBA em `img/map/icons/{numero}.png`.

Confiança (`confidence`) baixa é esperada e não é sinal de calibração errada: ícones tão pequenos (~17x17px) têm pouca informação de pixel, então pequenas diferenças de sub-pixel entre a captura do template e o momento da detecção derrubam o score de correlação mesmo em matches corretos. O padrão do Cavebot foi ajustado pra `confidence: 0.65` (contra 0.85 do AutoFood, que usa ícones bem maiores) - `~0.60` já é uma faixa segura de se usar, dado que a busca já é restrita à ROI pequena do mini mapa (baixo risco de falso positivo mesmo com confiança mais baixa).

## 1. Relatório de viabilidade

### 1.1 O que já existe e é 100% reutilizável sem alteração

| Necessidade | Componente existente | Onde |
|---|---|---|
| Captura de tela multi-monitor segura (mss) | `ScreenCapture` | `core/screen_capture.py` |
| Template matching (cv2) | `cv2.matchTemplate` já usado assim em `AutoFoodWorker._locate_icon` | `functions/auto_food.py:71-78` |
| Restringir busca à janela do jogo (evita falso positivo fora do client, já foi bug real neste projeto) | `background_input.client_screen_rect(hwnd)` | `core/background_input.py` |
| Clique em background, botão esquerdo OU direito | `background_input.post_click(hwnd, x, y, button)` e `InputSimulator.click(x, y, button="left", ...)` | `core/background_input.py`, `core/input_simulator.py:82-102` |
| Calibração manual de região (arrastar na tela) | `controller.select_region(hint)` → `region_selector.select_region` | `gui/qt/controller.py:153-154`, `gui/qt/region_selector.py:91-104` |
| Salvar um template de imagem calibrado em disco | `save_image` / `load_image` | `core/screen_capture.py` |
| Overlay visual de região (retângulo verde), sem OCR | `ManaOverlay`/`_RegionMarker` | `gui/qt/overlays/mana_overlay.py:14-26` (já reaproveitado por Training para a Battle List, não só mana) |
| Overlay que acompanha a janela do jogo entre monitores | `LogOverlay`/`FishingWarningOverlay` (padrão `hwnd_resolver` + `client_screen_rect` + reposiciona a cada tick/linha) | `gui/qt/overlays/log_overlay.py`, `gui/qt/overlays/fishing_warning_overlay.py` |
| Arbitragem de prioridade entre workers ("Priority Manager") | `AutomationCoordinator` (`PRIORITY_ORDER`, `request_floor`/`release_floor`/`should_pause`/`wait_for_higher_priority`) | `core/coordinator.py`, `core/worker.py:82-116` |
| Detecção "Battle List vazia" e "cor de ataque presente" | Funções livres `battle_list_empty_score`, `battle_list_is_empty`, `attack_color_present` (sem dependência de instância) | `functions/target.py:45-79` |
| Ciclo de vida de worker (setup/loop/teardown, pause/resume/stop, log, counter) | `BaseWorker` | `core/worker.py` |
| Esqueleto de tela de configuração por módulo (start/stop/toggle_pause/on_state/_on_module_event) | Padrão repetido em `FishingModuleView`/`TargetModuleView`/`TrainingModuleView`/`RuneMakerModuleView` | `gui/qt/dialogs/module_config/*.py` |

**Conclusão**: a base técnica (captura, detecção, clique, calibração, overlay, coordenação de prioridade) já existe quase inteira. O Cavebot é, na maior parte, uma **composição** desses blocos, não uma feature que exige infraestrutura nova.

### 1.2 O que precisa de adaptação mínima

- **`battle_list_empty_score`/`attack_color_present` como métodos de instância do Target** (`TargetWorker.is_battle_list_empty`/`is_attacking`, `functions/target.py:155-174`) dependem de `self.capture`/`self.battle_list_region`/`self.attack_rgb` — não são chamáveis de fora. Isso não é um problema se o Cavebot **não precisar ler a Battle List sozinho** (ver §1.4, opção recomendada) — só vira necessário se o Cavebot precisar rodar standalone sem o Target ligado.
- **`ManaOverlay`/`_RegionMarker`** já é reutilizado por dois módulos com propósitos diferentes (mana e Battle List do Training) sob um nome que não reflete isso. Não precisa mudar para o Cavebot funcionar, mas um rename para algo como `RegionMarkerOverlay` deixaria o código mais claro (cosmético, não bloqueante).
- **`STATE_LABELS`** (`gui/qt/components/status_badge.py:6-11`) só reconhece `running`/`paused`/`stopped`/`error`. O Cavebot deve **se limitar a esses 4 valores** no canal `"state"` — qualquer estado mais granular (ex. "procurando ícone", "andando") deve ser um canal de evento **separado** (ex. `"phase"`), seguindo o precedente já existente de `"elapsed"` e `"mana_reading"` (`functions/training.py:150,200`), e exibido como texto num stat do `ModuleCard` (não existe componente de progresso/barra — ver `gui/qt/components/module_card.py`, `statistic_card.py`).
- **`core/config.py`**: nenhuma seção hoje guarda uma lista ordenada de waypoints — o Cavebot será o primeiro módulo com esse formato de config. Não é uma mudança em código existente, é uma seção nova seguindo a convenção de nomenclatura já usada (`snake_case`, sufixos `_region`/`_key`/`_delay_min/max`/`_enabled`/`_threshold`).

### 1.3 O que é genuinamente novo

- **Detecção de ícone do mini mapa + conversão de coordenadas ROI→tela.** Análogo a `AutoFoodWorker`, mas novo (região diferente, ícones diferentes).
- **Máquina de rota (lista ordenada de pontos, índice atual, avanço/loop).** Não existe precedente nenhum no projeto.
- **Espera de deslocamento cancelável** (ver §1.5 — na prática é composição de primitivas existentes, não uma nova primitiva de temporização).
- **Loot.** Zero precedente no projeto (confirmado por busca ampla: nenhuma menção a "loot"/"corpse"/"cadáver"/"recolher item" em nenhum arquivo `.py`). Isto é 100% código novo, sem nada pra reaproveitar — incluindo a própria detecção visual de "corpo no chão" e a ação de clique/uso sobre ele.
- **Overlay do mini mapa com marcação da ROI**: reaproveita a *classe* de overlay existente, mas a instância/config (`cavebot.minimap_region`) é nova.

### 1.4 Ponto crítico de arquitetura — como o Cavebot deve saber que "tem monstro" (Passo 2.5)

O relatório pediu para avaliar se o Target expõe a leitura da Battle List de forma reutilizável. A resposta muda a proposta:

- Hoje, **Target e Training já leem a Battle List de forma independente e concorrente** (cada um com sua própria `ScreenCapture`, sua própria `battle_list_region` configurada separadamente em `core/config.py:109` e `:122`) — não existe nenhum bloqueio de leitura entre eles. A única coisa que é exclusiva é a **ação** (apertar a tecla de ataque), arbitrada pelo `AutomationCoordinator` via `request_floor`/`release_floor` (`functions/target.py:195,202`).
- **Isso muda a resposta para "quem monitora a Battle List durante a rota":** se o Cavebot rodar **junto com o Target já ligado** (dois workers, duas threads, ambos registrados no coordinator), o Target **já está** monitorando a Battle List e **já chama** `request_floor()` sozinho assim que decide atacar (`functions/target.py:184-195`). O Cavebot não precisa duplicar nenhuma leitura de Battle List — só precisa:
  1. Registrar-se no coordinator com prioridade **menor** que `"target"` (adicionar `"cavebot"` ao fim de `PRIORITY_ORDER` em `core/coordinator.py:5` — confirmado seguro: workers fora da lista caem no rank mais baixo por padrão, então só adicionar no fim não muda nenhum comportamento existente).
  2. Fatiar a espera de deslocamento em pequenos passos (ex. 200ms) chamando `self.wait_for_higher_priority()` entre eles (mesmo método que Fishing/Training/RuneMaker já usam) — isso já bloqueia sozinho enquanto o Target estiver com o "chão" pedido, sem o Cavebot precisar saber *por que* está pausado.
  3. Guardar o waypoint atual (`ponto_pendente`) como **atributo de instância do próprio `CavebotWorker`** — não precisa de estado compartilhado nem de um "Priority Manager" novo, porque a exclusão mútua já é feita pelo coordinator, e o Cavebot só continua para o próximo ponto quando a espera daquele ponto terminar sem interrupção.

- **Trade-off explícito**: essa abordagem (recomendada) exige que o usuário **ligue o Target junto com o Cavebot** para ter o comportamento "para de andar, luta, retoma". Se o objetivo é o Cavebot funcionar **sozinho** (sem o Target ativo) e ainda assim reagir a monstro, ele precisaria da sua própria leitura de Battle List — reaproveitando as *funções livres* (`battle_list_empty_score`, `attack_color_present`, já reutilizáveis, `functions/target.py:45-79`) mas com sua própria captura/região/estado, **duplicando** a parte de "decidir atacar" que hoje só existe dentro do `TargetWorker`. Isso é possível, mas é mais código e mais um lugar reimplementando a mesma decisão.
- **Loot não tem para onde apontar** — nem no fluxo A (com Target) nem no B (standalone) existe hoje qualquer detecção de "corpo no chão" ou ação de recolher. Ver §3 para proposta de descopo do v1.

### 1.5 Espera cancelável — não é uma primitiva nova

`BaseWorker.sleep(seconds)` (`core/worker.py:68-74`) já fatia a espera em passos de 50ms verificando `self.stopped`. `wait_for_higher_priority()` (`core/worker.py:92-107`) já bloqueia sozinho enquanto `coordinator.should_pause(name)` for verdadeiro. A "espera de deslocamento cancelável" do Cavebot é simplesmente: um laço que chama `wait_for_higher_priority()` e `self.sleep(0.2)` repetidamente até completar o tempo configurado do ponto, sem inventar nenhum mecanismo de tempo novo. Não há necessidade de mexer em `core/worker.py` — na pior das hipóteses, vale a pena adicionar um helper de conveniência (ex. `sleep_yielding(seconds)`) para não repetir esse laço em outro lugar no futuro, mas isso é opcional.

### 1.6 Risco a evitar explicitamente: calibração de ROI sem restrição de região

O usuário sugeriu usar `pg.locateOnScreen` pra auto-detectar a área do mini mapa quando não calibrada. **Atenção**: esse padrão (busca de imagem na tela inteira, via `pyautogui`, sem restringir a uma região) foi exatamente a causa raiz de um bug real já corrigido neste projeto no `AutoFood` (falso positivo reconhecendo item em qualquer lugar da tela, e crash em monitor secundário por má manipulação de coordenadas — ver histórico de commits `c81934f`, `f87a0e1`). Se uma auto-detecção da ROI do mini mapa for implementada, ela deve seguir o padrão **pós-correção** do AutoFood (`ScreenCapture` + `cv2.matchTemplate`, restrito ao retângulo do client via `background_input.client_screen_rect`), nunca uma chamada crua de `pyautogui` na tela inteira. Recomendação: tratar a auto-detecção como *nice-to-have* de uma fase posterior, e usar `controller.select_region` (calibração manual por arraste, já validada em Fishing/Target/RuneMaker) como mecanismo principal do v1.

---

## 2. Plano de implementação por módulo/responsabilidade

| Módulo/responsabilidade | Reutiliza | Adapta | Novo |
|---|---|---|---|
| **Config dos ícones/rota** (`cavebot.waypoints: [{"icon": "img/map/icons/1.png", "wait_s": 5}, ...]`) | Convenção de nomenclatura de `core/config.py` | — | Sim — primeira lista ordenada do projeto |
| **Localização de ícone no mini mapa** | `ScreenCapture` + `cv2.matchTemplate` (mesmo padrão de `AutoFoodWorker._locate_icon`, `functions/auto_food.py:71-78`) | — | Só a função de carregar os ícones de `img/map/icons/*.png` |
| **Calibração + overlay da ROI do mini mapa** | `controller.select_region` (calibração), `ManaOverlay`/`_RegionMarker` (marcação visual) | Instanciar overlay com a região do mini mapa em vez da região de mana | — |
| **Conversão ROI→tela** | `background_input.client_screen_rect` (limite da janela) + região absoluta calibrada (mesmo padrão de `battle_list_region`) | — | Uma função pequena que combina "ponto dentro da ROI" + "ROI dentro do client" — validação, não conversão complexa |
| **Validação pré-clique** (dentro do client, dentro da ROI, dentro da tela) | `client_screen_rect`, região calibrada | — | Função de validação combinando os dois (trivial) |
| **Clique em background, botão esquerdo** | `InputSimulator.click(x, y, button="left")` / `background_input.post_click(..., "left")` | Nenhuma — já suporta botão esquerdo | — |
| **Timeout de busca separado do tempo de deslocamento** | Padrão de retry do AutoFishing (`maybe_take_break`, `sleep`+`continue`) | — | Loop de busca com timeout próprio antes de clicar |
| **Espera de deslocamento cancelável** | `BaseWorker.sleep` + `wait_for_higher_priority` (ver §1.5) | — | Só o laço de composição |
| **Máquina de estados (badge)** | `BaseWorker` (`running`/`paused`/`stopped`/`error`) | — | — |
| **Sub-fase interna (procurando/andando/parado por combate)** | Precedente de `"elapsed"`/`"mana_reading"` como canais de evento extras | Novo `kind="phase"` no `emit`, exibido via `ModuleCard.set_stat` | Pequeno |
| **Registro de prioridade / integração com Target** | `AutomationCoordinator`, `wait_for_higher_priority`, `request_floor` já chamado pelo Target | Adicionar `"cavebot"` a `PRIORITY_ORDER` (`core/coordinator.py:5`) | — |
| **`ponto_pendente`** | — | — | Atributo de instância do `CavebotWorker` (ver §1.4 — não precisa de estado compartilhado) |
| **Ataque ao monstro** | Lógica já existente no `TargetWorker` rodando em paralelo (recomendado) | — | Só se decidir pelo modo standalone (duplicaria detecção) |
| **Loot** | Nada | — | 100% novo — detecção visual do corpo + ação de clique/uso. Recomendo tratar como incremento separado (ver Ordem sugerida) |
| **Tela de configuração (`CavebotModuleView`)** | Esqueleto padrão de `TargetModuleView`/`TrainingModuleView` | — | Nova view seguindo o padrão |

---

## 3. Ordem sugerida de implementação

1. **Rota "pura" (sem Target)** — config de waypoints, calibração + overlay da ROI, localização de ícone restrita à ROI, validação pré-clique, clique em background botão esquerdo, espera bloqueante simples (ainda não cancelável), timeout de busca separado do tempo de deslocamento, máquina de estados básica. **Testável isoladamente**, sem depender de nada do Target.
2. **Espera cancelável + integração com prioridade** — trocar a espera bloqueante por `wait_for_higher_priority` fatiado, adicionar `"cavebot"` a `PRIORITY_ORDER`. Ainda testável sozinho (sem Target rodando, o comportamento é idêntico ao passo 1; com Target rodando, já deve pausar/retomar mesmo antes de qualquer lógica de loot).
3. **Integração Cavebot↔Target (combate)** — `ponto_pendente`, ciclo "detectado→ataca→verifica de novo→retoma". Depende 100% do Target estar rodando (modo recomendado do §1.4). Testável com Target manualmente ligado ao lado.
4. **Loot** — increment separado, depois de validar 1–3. Proponho descopar a ação real de loot do v1 se o prazo apertar: nesse caso, o passo 5 do fluxo do usuário vira "não faz nada, só espera a Battle List ficar vazia de novo antes de retomar" — funcional, só sem recolher o item.
5. **Polimento**: sub-fase (`"phase"`) no card, rename opcional de `ManaOverlay`→algo mais genérico, helper `sleep_yielding` em `BaseWorker` se o padrão se repetir em outro módulo.

---

## 4. Perguntas em aberto

1. **Modo recomendado (§1.4) exige Target ligado.** Isso é aceitável, ou o Cavebot precisa reagir a monstro mesmo com o Target desligado (aumentando o escopo pra incluir leitura própria da Battle List, duplicando parte da decisão de ataque)?
2. **Loot**: descopar do v1 (Cavebot só espera a área ficar livre e retoma a rota, sem recolher item) ou é obrigatório já na primeira versão? Se obrigatório, preciso de referência visual (ícone/cor do corpo, ou é um clique numa posição relativa fixa?) pra desenhar a detecção do zero.
3. **Sub-estado visual**: quer ver "procurando ícone / andando / parado por combate" no card do Cavebot (via novo canal de evento `"phase"` + stat de texto), ou o badge padrão (rodando/pausado/parado/erro) já é suficiente por enquanto?
4. **Intervalo de polling da Battle List**: se o modo standalone (pergunta 1) for necessário, qual intervalo é seguro dado o hardware alvo? Sugiro começar com o mesmo `idle_delay_min/max` (2–4s) já usado pelo Target como referência, ajustável depois.
5. **Nome do worker/config**: `"cavebot"` como chave de config e `name_label`, ou outro nome já em mente (ex. `"movement"`, separando "rota" de "cavebot completo com combate" como dois conceitos)?
