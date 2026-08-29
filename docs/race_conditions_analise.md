# Race Conditions entre Workers — Análise

Documento de análise, sem implementação ainda. Baseado em levantamento preciso do código atual (todas as referências arquivo:linha vêm do estado do repositório nesta data).

## 1. Como cada worker participa da coordenação hoje

O `AutomationCoordinator` (`core/coordinator.py`) só protege de verdade um worker contra outro se **os dois** participarem corretamente: registrar-se, ceder quando alguém de prioridade maior estiver ativo (`wait_for_higher_priority`), e **segurar a prioridade durante toda a ação física** (`request_floor`/`release_floor`) - não só checar antes.

| Worker | Registrado? | Cede prioridade (`wait_for_higher_priority`)? | Segura o floor ao redor da ação física? | Ação física | Rank em `PRIORITY_ORDER` |
|---|---|---|---|---|---|
| **AutoFood** | **Não** | Não | Não (nem participa) | clique direito (`background_input.post_click`, `functions/auto_food.py:58,108`) | fora da lista (equivale ao rank mais baixo, mas isso é irrelevante já que nem se registra) |
| **AutoFishing** | Sim (`"fishing"`) | Sim, só no topo do loop (`functions/auto_fishing.py:282`) | **Não** | `mouse.click` (`functions/auto_fishing.py:323,328`) | 3 (penúltimo) |
| **Cavebot** | Sim (`"cavebot"`) | Sim, em 3 pontos (`functions/cavebot.py:140,111,197`) | **Não** | `mouse.click` (`functions/cavebot.py:132`, chamado via `:169,:204`) | 4 (último) |
| **RuneMaker** | Sim (`"runemaker"`) | Sim | **Sim**, ao redor de todo ciclo de craft/cast (`functions/rune_maker.py:225/229-232`, `:265/269-272`) | `press_key`/`click`/`drag` | 2 |
| **Target** | Sim (`"target"`) | Sim | **Sim**, ao redor de toda a luta (`functions/target.py:231/236-239`) | `press_key` (só teclado) | 0 (máxima) |
| **Training** | Sim (`"training"`) | Sim | **Sim**, em 3 pontos (anti-afk, ataque, magia) | `press_key` (só teclado) | 1 |

**Confirmação do que você já tinha percebido**: Target e a magia do Training/RuneMaker usam só teclado, e os dois já protegem a ação com `request_floor`/`release_floor` - por isso "já tem um pouco de mitigação". O problema real está nos workers que usam **mouse**: AutoFood, AutoFishing e Cavebot.

## 2. Cenários concretos de conflito

### 2.1 AutoFood — risco mais alto (nenhuma proteção)

AutoFood não se registra no coordinator, não checa nada antes de clicar, e clica (botão direito) a qualquer momento em que reconhece o ícone de comida. Isso significa que ele pode clicar:

- **No meio de um `_engage()` do Target/Training** (que estão segurando o floor, mas isso não impede AutoFood - o floor só bloqueia quem *pede* prioridade, não quem ignora o sistema).
- **No meio de um drag do RuneMaker** (que está segurando o floor durante múltiplos `drag()` seguidos - se o clique direito do AutoFood cair no meio de um desses drags, pode confundir o estado do drag ou, dependendo de como o client trata mensagens simultâneas, fazer o RuneMaker "soltar" o item no lugar errado).
- **No meio do clique do Cavebot no mini mapa.**

Esse é o worker que mais precisa de correção: registrar no coordinator e envolver o clique em `request_floor`/`release_floor`, igual ao RuneMaker já faz.

### 2.2 AutoFishing e Cavebot — proteção parcial (checam mas não seguram)

Os dois fazem a checagem (`wait_for_higher_priority`/`should_pause`) **antes** de começar a processar, mas entre essa checagem e o clique de fato existe uma janela (captura de tela + processamento de imagem, alguns milissegundos a poucas dezenas de ms) onde um worker de prioridade maior pode assumir o floor **depois** da checagem e **antes** do clique - nesse caso o fishing/cavebot ainda executa o clique, porque não voltou a checar logo antes de clicar nem pediu o floor pra si.

Na prática, essa janela é curta, mas existe. Cavebot e AutoFishing nunca competem diretamente entre si hoje (raramente alguém liga os dois ao mesmo tempo - fishing é uma atividade parada, cavebot é movimentação), mas os dois podem colidir com AutoFood (que também não tem proteção nenhuma) ou, na janela específica citada, com o início de uma ação do Target/Training/RuneMaker.

### 2.3 O cenário que você descreveu: Cavebot + Target + AutoFood + RuneMaker(mana training) juntos

Ordem de prioridade hoje: Target (0) > Training (1) > RuneMaker (2) > AutoFishing (3) > Cavebot (4). **AutoFood não está na lista - não compete com ninguém, é uma ameaça "invisível" pro sistema.**

- Target ataca (segura floor) → RuneMaker/Cavebot corretamente pausam (RuneMaker via `request_floor` bloqueando, Cavebot via `should_pause`) ✔️
- RuneMaker conjura magia de mana (segura floor) → Cavebot pausa corretamente (rank menor) ✔️. Mas **Target não seria pausado por RuneMaker** mesmo que RuneMaker tivesse prioridade maior, porque a lista já reflete isso como esperado (RuneMaker é rank 2, menor que Target) - ok, é o comportamento certo mesmo.
- **AutoFood não pausa por ninguém, e ninguém pausa por causa dele.** Ele pode clicar bem no meio de qualquer um dos cenários acima, a qualquer momento.

## 3. Um segundo tipo de risco, diferente: o cursor real do usuário

Isso é uma categoria totalmente separada da coordenação entre workers, e você já percebeu isso na prática: **alguns clients de Tibia (confirmado pelo usuário: o client Miracle) leem a posição real do cursor do sistema pra processar cliques, em vez de confiar só nas coordenadas da mensagem enviada** (isso já está registrado como conhecimento do projeto). Isso quer dizer:

- Nenhuma quantidade de coordenação entre os NOSSOS workers resolve esse problema, porque o conflito não é bot-vs-bot, é **bot-vs-você**: se você move o mouse de verdade dentro do client enquanto qualquer worker envia um clique em background, o client pode processar esse clique na posição de onde seu mouse real está, não na posição que o bot mirou.
- Isso é uma limitação do client, não um bug que dá pra corrigir só ajustando o coordinator. As opções realistas são: (a) documentar e avisar o usuário pra evitar mexer no mouse dentro do client enquanto os bots estão ativos (parecido com o aviso que já existe no AutoFishing), ou (b) uma alternativa mais invasiva de mover o cursor real momentaneamente pro clique (trade-off que reintroduz o "sem mexer no seu mouse" que o projeto quer evitar).

## 4. Recomendação de prioridade de correção (sem implementar ainda)

1. **AutoFood**: registrar no coordinator (ex. rank igual ou logo abaixo de `fishing`) e envolver o clique em `request_floor`/`release_floor`, mesmo padrão do RuneMaker. É o risco mais alto e o mais barato de corrigir (poucas linhas).
2. **AutoFishing e Cavebot**: envolver o clique final (não só a busca) em `request_floor`/`release_floor`, fechando a janela entre checagem e ação.
3. **Aviso ao usuário** (UI, tipo o aviso já feito no AutoFishing) sobre não mexer o mouse dentro do client dos clients que leem cursor real, reforçando que isso é uma limitação do client, não um bug do app.

Nenhuma dessas correções é grande - são mudanças localizadas, seguindo exatamente o padrão que RuneMaker/Target/Training já usam. Fica pra decidir se implementamos as três agora ou uma de cada vez.
