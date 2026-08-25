# EasyF

Automação de duas tarefas repetitivas do Tibia (OTClient/OTC e similares) feita
**100% por pixels da tela + simulação de mouse e teclado**.

O que este programa **não** faz, por decisão de projeto:

- não lê nem escreve na memória do processo do jogo;
- não injeta DLL, não faz hooking nem qualquer alteração no cliente;
- não tenta se esconder do sistema operacional (nome de processo, ícone e
  metadados são honestos);
- não resolve nem responde captchas / desafios anti-bot;
- não faz nenhuma comunicação de rede: sem telemetria, sem licenciamento remoto.

> **Aviso importante:** usar automação pode violar os termos de uso do
> servidor/jogo e resultar em **banimento da conta**. Este software apenas
> simula mouse e teclado; a decisão de usar (e o risco) é inteiramente do
> usuário. Em servidores oficiais isso é proibido. Prefira testar em servidor
> próprio ou onde a prática seja explicitamente permitida.

---

## Funcionalidades

### 1. AutoFishing
Monitora uma região da tela escolhida por você, identifica tiles de água e
clica nelas com a vara de pesca equipada.

- Detecção por **cor (HSV)** ou por **template** (`cv2.matchTemplate`).
- Calibração feita a partir de um recorte da sua própria tela.
- Clique com botão direito ou esquerdo (configurável), com variação de ±N pixels.
- Intervalo aleatório entre lances (`random.uniform`), configurável.
- Contador de lances da sessão e log com horário de cada ação.

> O contador conta **lances (tentativas de pesca)**, não peixes. Como o
> programa só enxerga pixels, ele não tem como confirmar que um peixe entrou na
> bag — contar lances é o número honesto.

### 2. RuneMaker
Cria runas em sequência clicando na blank rune e acionando a hotkey da magia.

- Hotkey da magia e slot da blank rune configuráveis (slot selecionado com um
  clique na tela).
- **Leitura de soul points e mana por OCR** (Tesseract) em regiões que você
  delimita na barra de status.
- Pausa automática quando soul ou mana ficam abaixo do mínimo definido
  (evita spam de magia sem recurso).
- Para sozinho ao atingir a quantidade configurada.
- Contador de runas criadas e log da sessão.

### Comum às duas
- GUI em `tkinter` com uma aba por função.
- Configurações salvas em `config.json` e recarregadas na abertura.
- Delays sempre aleatórios dentro do intervalo que você definir.
- Hotkeys globais: **F6** pausa/retoma, **F7** para tudo (configuráveis).
- **Escape de emergência:** mover o mouse para o canto superior esquerdo da
  tela aborta o script imediatamente (fail-safe do PyAutoGUI).

---

## Instalação

Requer **Python 3.11+** (Windows recomendado, pois é onde o cliente roda).

```bash
git clone <este-repositorio> tibia-assist
cd tibia-assist

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

pip install -r requirements.txt
```

### Tesseract (apenas para o RuneMaker)

O OCR de soul/mana usa o Tesseract, que é um programa separado:

1. Baixe e instale: <https://github.com/UB-Mannheim/tesseract/wiki>
2. Se ele não estiver no `PATH`, informe o caminho completo no campo
   **"Caminho do Tesseract"** da aba RuneMaker, por exemplo:
   `C:\Program Files\Tesseract-OCR\tesseract.exe`

Se preferir não usar OCR, desmarque "Verificar soul points" e "Verificar mana" —
os limites de segurança automáticos ficam desligados e o controle passa a ser
seu (use o campo "Quantidade de runas" para limitar).

## Execução

```bash
python main.py
```

> **Rode como Administrador se o cliente do jogo tambem rodar como Administrador.**
> O Windows usa UIPI (User Interface Privilege Isolation) para bloquear
> silenciosamente cliques e teclas sinteticos vindos de um processo de
> privilegio mais baixo quando o alvo e uma janela elevada - o cursor se move
> normalmente (e um estado global do sistema), mas os cliques simplesmente nao
> tem efeito, sem nenhum erro visivel. Se os cliques nao estiverem funcionando
> mas a deteccao e o movimento do mouse estiverem corretos, esse e o primeiro
> lugar para verificar. O `.exe` gerado pelo `build.bat` ja pede elevacao
> automaticamente ao abrir.

---

## Como configurar

### AutoFishing

1. **Região monitorada** — clique em *Selecionar região* e arraste um retângulo
   sobre a área de água do hunt. Quanto menor a região, mais rápido e mais
   preciso. `ESC` cancela a seleção.
2. **Calibrar a detecção** (escolha uma das duas):
   - *Calibrar cor da água*: arraste um retângulo pequeno **sobre a água**. O
     programa calcula a faixa HSV a partir da mediana dos pixels e preenche os
     campos "HSV mínimo/máximo". É o modo mais tolerante a variações.
   - *Capturar template*: selecione **uma única tile** de água. A imagem é
     salva em `assets/water_template.png` e usada com `cv2.matchTemplate`. Mais
     preciso quando o sprite é sempre igual; mais sensível a zoom e resolução.
3. **Testar detecção** — roda a detecção uma vez e mostra no log quantas tiles
   foram encontradas. Ajuste `Área mínima` (modo HSV) ou `Threshold` (modo
   template) até achar só o que interessa.
4. **Ritmo** — `Delay mínimo/máximo` define a espera aleatória entre lances
   (padrão 1.8s–3.2s, próximo da animação de pesca). `Variação do clique`
   define o jitter em pixels.
5. Clique em **Iniciar**, foque a janela do jogo e deixe rodar.

### RuneMaker

1. **Tecla da magia** — a mesma hotkey que você configurou dentro do jogo para
   a magia de criação (ex.: `f2` para `adori gran mort`).
2. **Slot da blank rune** — clique em *Selecionar slot* e depois clique sobre a
   blank rune na sua backpack.
3. **Regiões de OCR** — selecione retângulos justos ao redor **apenas do número**
   de soul e de mana na barra de status. Use *Testar OCR* para conferir se o
   valor lido bate com a tela; se não bater, refaça a seleção mais justa ao
   número e sem elementos ao redor.
4. **Limites de segurança** — `Soul mínimo` e `Mana mínima`. Abaixo disso o
   ciclo espera e volta a checar, em vez de conjurar sem recurso.
5. **Quantidade** — `0` significa criar até acabar soul/mana ou até você parar.
6. **Ritmo** — mantenha o `Delay mínimo` **igual ou maior que o cooldown real
   da magia** no seu servidor (padrão 1.5s–2.5s).

### Hotkeys globais

No topo da janela você define as teclas de **pausar/retomar** e **parar tudo**
(padrão `F6` e `F7`) e clica em *Aplicar*. Elas funcionam com o jogo em foco.

No Linux o módulo `keyboard` exige privilégios de root; se ele não conseguir
registrar as hotkeys, a mensagem aparece na barra de status e você usa os
botões da interface.

---

## Estrutura do projeto

```
easyf/
  main.py                      # ponto de entrada + checagem de dependências
  requirements.txt
  config.json                  # criado na primeira execução
  core/
    config.py                  # defaults + persistência em JSON
    screen_capture.py          # captura de tela via mss (frames BGR)
    region_selector.py         # overlay tkinter para escolher região/ponto
    input_simulator.py         # cliques e teclas com jitter e delays aleatórios
    worker.py                  # thread base com pause/stop e fila de eventos
  functions/
    auto_fishing.py            # detecção de água (HSV/template) + ciclo de pesca
    rune_maker.py              # OCR de soul/mana + ciclo de criação de runas
  gui/
    app.py                     # janela principal, abas, hotkeys, fila de eventos
    fishing_window.py          # aba AutoFishing
    runemaker_window.py        # aba RuneMaker
    widgets.py                 # widgets auxiliares (log, campos, parsers)
  assets/                      # templates calibrados (ex: water_template.png)
```

As rotinas rodam em threads separadas e **nunca** tocam widgets do tkinter
diretamente: elas publicam eventos numa `queue.Queue` que a janela principal
drena no loop do tkinter.

---

## Gerando o executável (Windows)

O PyInstaller **não faz cross-compile**: o `EasyF.exe` precisa ser gerado
em uma máquina Windows (com o Python 3.11+ instalado). Copie o projeto para lá e
rode, na pasta do projeto:

```bat
build.bat            :: build normal, sem janela de console
build.bat debug      :: build com console - use no primeiro teste
```

O script cria o `.venv`, instala as dependências e o PyInstaller, e gera
`dist\EasyF.exe`. Recomendo o **primeiro build em modo `debug`**: se
faltar alguma dependência ou algo falhar ao abrir a janela, o traceback aparece
no console em vez de o programa fechar em silêncio.

Os metadados do executável ficam em `version_info.txt` (nome, descrição, autor,
copyright) — ajuste com o seu nome real. O nome do binário, o ícone e a
descrição devem dizer honestamente o que o programa é: **não** renomeie para se
passar por processo do Windows ou de terceiros.

### Onde ficam os arquivos no executável

Rodando como `.exe`, o `config.json` e a pasta `assets/` ficam **ao lado do
executável**, não na pasta temporária do PyInstaller — então as configurações e
o template calibrado sobrevivem entre execuções. Mantenha o `.exe` numa pasta
onde seu usuário tenha permissão de escrita (evite `C:\Program Files`).

### Observações

- O **Tesseract OCR** não é embutido no executável: ele é um programa separado e
  precisa estar instalado na máquina que for rodar o RuneMaker.
- O build usa `upx=False` de propósito — executáveis comprimidos com UPX viram
  falso positivo de antivírus com frequência.
- É normal o Windows Defender ou o SmartScreen alertarem sobre um `.exe` novo e
  sem assinatura digital; isso vale para qualquer binário recém-compilado.

## Solução de problemas

| Sintoma | O que verificar |
|---|---|
| "Nenhuma tile de água encontrada" | Recalibre a cor com um recorte só de água; reduza `Área mínima`; confira se a região selecionada é a certa |
| Detecta grama/parede como água | Aumente `Área mínima`, recalibre com um recorte mais puro ou use o modo template |
| Mouse se move certinho mas o clique não tem efeito | O cliente do jogo provavelmente roda como Administrador. Execute o EasyF (ou o `.exe`) também como Administrador — Windows bloqueia silenciosamente input sintético de um processo de privilégio mais baixo chegando numa janela elevada (UIPI) |
| Cliques não têm efeito no jogo (mesmo nível de privilégio) | O cliente pode ignorar input sintético em modo tela cheia — tente janela/janela sem borda |
| Template para de funcionar | Zoom ou resolução mudaram; capture o template de novo |
| OCR lê valor errado ou nada | Selecione um retângulo mais justo, só com o número; confira o caminho do Tesseract em *Testar OCR* |
| Hotkeys não respondem | Execute como administrador (Windows) / root (Linux) ou use os botões da interface |
| Preciso parar já | Mova o mouse para o canto superior esquerdo da tela (fail-safe) |

---

## Licença e responsabilidade

Código fornecido como está, para uso pessoal e educacional. Ao usar, você
assume integralmente o risco de sanções aplicadas pelo servidor/jogo, incluindo
banimento de conta.
