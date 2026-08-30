# AutoLoot — Relatório de Viabilidade

Documento de referência antes da implementação (padrão já usado em `docs/cavebot_plano.md`).

## 0. Fluxo confirmado com o usuário

1. Target engaja um monstro. Numa área demarcada pelo usuário (necessária porque em servidores old-school a cave é escura e o monstro pode não aparecer visualmente mesmo com a Battle List mostrando o ataque), monitoramos a mesma cor RGB já usada pelo Target (`attack_color_rgb`/`tolerance`/`min_pixels`) - só que aqui não é lida na Battle List, é lida na tela do jogo.
2. Enquanto a cor estiver presente, guardamos a última posição (centro) onde ela foi vista.
3. Quando a cor some (transição presente→ausente), é o sinal de morte. Nesse momento devemos segurar a prioridade (pra Target não iniciar outro ataque, nem Cavebot andar, antes do loot).
4. Clique com botão direito na posição guardada, abrindo o corpo.
5. Configuração prévia: região da bag de origem (corpo já aberto) e ponto/região da bag de destino, mais uma lista de ícones de item de loot capturados ao vivo (mesmo processo já validado no Cavebot: recorte + captura ao vivo).
6. Repetir a varredura da bag de origem contra a lista de itens desejados até não sobrar nenhum configurado, arrastando cada item encontrado pro destino.
7. Ao esvaziar, soltar a prioridade e voltar ao fluxo normal: Target verifica de novo, depois Cavebot anda.

## 1. O que já existe e é 100% reutilizável sem alteração

| Necessidade | Componente existente | Onde |
|---|---|---|
| Captura de tela restrita a uma região | `ScreenCapture.grab(region)` | `core/screen_capture.py` |
| Calibração manual de região (arrastar) | `controller.select_region(hint)` | `gui/qt/controller.py`, `gui/qt/region_selector.py` |
| Calibração manual de ponto único (clique) | `controller.select_point(hint)` | mesmo módulo, já usado pelo `rod_slot` do Fishing |
| Overlay visual de região (retângulo verde, sem label) | `ManaOverlay(parent)` sem `log_overlay` - já é assim que o Cavebot demarca o mini mapa | `gui/qt/overlays/mana_overlay.py`, uso em `CavebotModuleView.__init__` |
| Detecção de cor RGB com tolerância | `attack_color_present(frame, rgb, tolerance, min_pixels)` | `functions/target.py:66-79` |
| Template matching de ícone | `cv2.matchTemplate` (mesmo padrão do `CavebotWorker._locate_icon`) | `functions/cavebot.py:97-105` |
| Captura + salvamento de template ao vivo | `select_region` + `ScreenCapture().grab()` + `save_image()` (mesmo padrão do `capture_template` do Fishing e do `capture_empty_template` do Target) | `gui/qt/dialogs/module_config/fishing.py:288-301`, `target.py:234-248` |
| Clique em background botão direito | `InputSimulator.click(x, y, button="right")` | `core/input_simulator.py:82-102` |
| **Arrastar item (drag) em background** | `InputSimulator.drag(from_x, from_y, to_x, to_y, ...)` → `background_input.post_drag` | `core/input_simulator.py:110-137`, `core/background_input.py:100-118` — **já implementado, mas sem nenhum consumidor hoje** |
| Arbitragem de prioridade | `AutomationCoordinator` (`PRIORITY_ORDER`, `request_floor`/`release_floor`/`wait_for_higher_priority`) | `core/coordinator.py`, `core/worker.py:82-116` |
| Ciclo de vida de worker | `BaseWorker` | `core/worker.py` |
| Esqueleto de tela de configuração (ModuleCard + `_ConfigDialog` + lista editável com add/editar/remover/mover) | Padrão do `CavebotModuleView` (lista de waypoints) | `gui/qt/dialogs/module_config/cavebot.py` |

**Conclusão**: assim como o Cavebot, o AutoLoot é majoritariamente composição. A única peça genuinamente nova é o algoritmo de rastrear-a-última-posição-antes-de-sumir e a sequência de abrir corpo + arrastar itens.

## 2. O que precisa de adaptação mínima

- `attack_color_present` retorna só `bool`. Precisamos também do **centróide** do blob de cor pra saber onde clicar. Proposta: nova função livre `attack_color_centroid(frame, rgb, tolerance, min_pixels) -> tuple[int, int] | None` em `functions/auto_loot.py` (ou promovida pra `functions/target.py` se fizer mais sentido reaproveitar o mesmo arquivo - decisão do implementador, mas **sem** duplicar a lógica de máscara já existente em `attack_color_present`; extrair a máscara pra uma função auxiliar comum e as duas (`_present`, `_centroid`) reaproveitam).
- `ManaOverlay` está sendo usado (terceira vez, depois de mana e mini mapa do Cavebot) só pelo retângulo verde, sem o label de valor. Continua sem precisar de mudança nenhuma - só reforça que um rename futuro pra algo como `RegionMarkerOverlay` seria cosmético e não bloqueante (mesma observação já registrada no plano do Cavebot).
- Aviso de "client sensível à posição real do cursor" em `gui/qt/pages/settings.py` (`_build_background_box`) lista os módulos afetados por nome - precisa incluir "AutoLoot" nessa frase.

## 3. O que é genuinamente novo

- **Rastreamento de última posição visível antes do sumiço** (transição presente→ausente com centróide guardado). Sem precedente no projeto.
- **Sequência de loot**: abrir corpo (clique direito numa posição dinâmica, não calibrada) → varrer região da bag de origem contra lista de templates → arrastar cada match pro destino → repetir até não achar mais nada configurado. Zero precedente (confirmado: nenhuma menção a loot/corpse no projeto antes desta feature).
- **Config de lista de itens de loot com captura ao vivo de ícone** - mesma mecânica de lista do Cavebot (add/editar/remover/mover), mas cada item aqui é capturado pelo próprio usuário na hora (não vem pré-pronto como os ícones 1-15 do mini mapa).

## 4. Decisão de prioridade (`PRIORITY_ORDER`)

Hoje: `["target", "training", "runemaker", "fishing", "auto_food", "cavebot"]`.

Proposta: inserir `"auto_loot"` logo depois de `"target"`:

```
PRIORITY_ORDER = ["target", "auto_loot", "training", "runemaker", "fishing", "auto_food", "cavebot"]
```

Motivo: o AutoLoot precisa impedir Cavebot/Fishing/RuneMaker/AutoFood/Training de agir enquanto abre o corpo e arrasta itens (mesma exclusividade que qualquer clique de rotina já usa via `request_floor`), mas o **Target precisa poder interromper o AutoLoot** se um monstro novo aparecer no meio do loot (Target é sempre a prioridade mais alta). Colocar `auto_loot` logo abaixo de `target` no rank garante os dois lados: `request_floor` do AutoLoot pausa tudo abaixo dele, e o próprio AutoLoot obedece `wait_for_higher_priority()` entre cada ação (igual Cavebot já faz), então para na hora se o Target pedir o chão de volta.

## 5. Fora de escopo desta primeira versão (documentado, não implementar)

- Múltiplos corpos simultâneos (só rastreia a posição do último sumiço; matar vários monstros em sequência rápida sem dar tempo de lotar cada corpo não é coberto).
- Calibração automática da região do corpo (`corpse_region`) - é fixa, calibrada uma vez manualmente, assumindo que a janela do container sempre abre no mesmo lugar.
- Leitura de nome de item via OCR - só reconhecimento por ícone (igual ao Cavebot).
- Lidar com o diálogo de quantidade que o Tibia às vezes abre pra itens empilháveis (ex. "mover quantos?") - se isso travar o fluxo, é um problema pra uma iteração posterior.
- Priorização/ordem de valor dos itens de loot além da ordem da lista.

## 6. Riscos já conhecidos deste projeto que se aplicam aqui

- **Client com cursor real** (ex. Miracle): clique direito ou arraste podem cair no lugar errado se o usuário mexer o mouse dentro do jogo durante o loot - mesmo risco documentado, só precisa entrar no aviso já existente.
- **DPI awareness**: já corrigido globalmente em `main.py`, nada a fazer aqui.
- **Confiança de template baixa por ícone pequeno**: mesma lição do Cavebot (`docs/cavebot_plano.md` seção 0) - ícones de item de inventário costumam ser maiores que os marcadores do mini mapa (mais parecido com os ícones do AutoFood), então uma confiança inicial mais alta (0.80-0.85) deve funcionar, mas o padrão de captura ao vivo (nunca de uma tela de menu/legenda) continua valendo.
