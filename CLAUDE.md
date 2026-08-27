# tibia-assist

App desktop (Tkinter, Windows) de automação/assistência para Tibia. Estrutura:
- `core/` — coordenação de workers, input simulator, captura de tela, OCR, licença, config, updater
- `gui/` — janelas Tkinter (main app, runemaker, target, training, fishing, overlays)
- `functions/` — workers de automação (ex: auto_food)

## Regras do projeto (hard rules)

- **Zero comentários no código.** Nunca escrever `#` comments nem docstrings narrativas, em nenhum arquivo, nenhuma exceção. Deixe nomes e estrutura carregarem o significado.
- **Texto PT-BR visível ao usuário sempre com acentuação correta** (labels, botões, mensagens de messagebox, logs exibidos na UI). Não usar grafia sem acento ("nao", "configuracao"). Não acentuar identificadores Python, chaves de dict/JSON/config, discriminadores internos de string (`"training"`, `"active"`), hotkeys literais (`"space"`, `"f7"`) ou paths.
- Threads/workers em `core/coordinator.py` e `functions/` rodam fora da main thread do Tkinter — qualquer atualização de widget deve voltar pra main thread (via `queue`, `.after()`, etc). Nunca tocar widget Tkinter direto de outra thread.

## Delegação de tarefas para subagents

Para qualquer tarefa não trivial (investigar bug, revisar mudanças, refatorar, avaliar um worker/coordinator), delegue para um subagent especializado em vez de resolver tudo na sessão principal. Tarefas triviais (ajuste de 1-2 linhas, resposta a uma pergunta pontual) podem ficar na sessão principal.

Subagents disponíveis em `.claude/agents/`:
- `code-reviewer` — revisa diffs/mudanças: bugs, thread-safety, recursos não liberados (captura de tela, processos), aderência às regras do projeto acima
- `debugger` — investiga bugs específicos (worker travando, OCR errando, hotkey não disparando, etc)
- `refactorer` — simplifica/reorganiza código existente sem mudar comportamento

Cada subagent roda em instância isolada (sem memória de invocações anteriores). Inclua contexto específico (arquivos, sintoma, linhas) no prompt de delegação.

Para tarefas em escala (auditar muitos arquivos, aplicar a mesma mudança em vários lugares em paralelo), use o tool `Workflow` em vez de subagents avulsos.
