import "dotenv/config";
import { readFile } from "fs/promises";

const CHANNEL_ID = "1542694182156771368";
const TOKEN = process.env.DISCORD_BOT_TOKEN;
const IMG_DIR = "C:/Users/Rennan Calixto/Projects/tibia-assist/docs/tutorial/images";

if (!TOKEN) {
  console.error("DISCORD_BOT_TOKEN ausente");
  process.exit(1);
}

async function postText(content) {
  const res = await fetch(`https://discord.com/api/v10/channels/${CHANNEL_ID}/messages`, {
    method: "POST",
    headers: { Authorization: `Bot ${TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) {
    console.error(`Falha (${res.status}):`, await res.text());
    process.exit(1);
  }
  console.log("Postado (texto).");
}

async function postImage(fileName, caption) {
  const fileBuffer = await readFile(`${IMG_DIR}/${fileName}`);
  const boundary = `----easyf${Date.now()}`;
  const payloadJson = JSON.stringify({ content: caption });
  const parts = [
    Buffer.from(
      `--${boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\nContent-Type: application/json\r\n\r\n${payloadJson}\r\n`
    ),
    Buffer.from(
      `--${boundary}\r\nContent-Disposition: form-data; name="files[0]"; filename="${fileName}"\r\nContent-Type: image/png\r\n\r\n`
    ),
    fileBuffer,
    Buffer.from(`\r\n--${boundary}--\r\n`),
  ];
  const res = await fetch(`https://discord.com/api/v10/channels/${CHANNEL_ID}/messages`, {
    method: "POST",
    headers: { Authorization: `Bot ${TOKEN}`, "Content-Type": `multipart/form-data; boundary=${boundary}` },
    body: Buffer.concat(parts),
  });
  if (!res.ok) {
    console.error(`Falha ao postar ${fileName} (${res.status}):`, await res.text());
    process.exit(1);
  }
  console.log(`Postado: ${fileName}`);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const sections = [
  {
    file: "01-dashboard.png",
    caption:
      "**1. Visão geral do Dashboard**\n\n" +
      "O Dashboard é a tela inicial do EasyF e reúne todos os módulos de automação em forma de cartões (ModuleCard). Cada cartão traz:\n" +
      "• Um selo de estado no canto superior direito (Parado, Rodando, Pausado).\n" +
      "• Botões Iniciar, Pausar/Retomar, Parar e Configurar... (abre a tela de configuração daquele módulo).\n" +
      "• Um contador (ex: \"Lances na sessão\", \"Pontos percorridos\", \"Itens recolhidos\") atualizado em tempo real.\n\n" +
      "Os seis módulos disponíveis são **AutoFishing**, **RuneMaker**, **Target**, **Training**, **Cavebot** e **AutoLoot**.\n\n" +
      "Logo abaixo, a seção **Opções** traz ajustes gerais:\n" +
      "• **Modo teste**: nenhum clique/tecla real é enviado ao jogo - útil pra testar sem risco.\n" +
      "• **Auto Food**: liga/desliga a comida automática (sem tela própria).\n" +
      "• **Logs na tela do jogo** + **Calibrar área do chat...**: mostra um balão de log sobre a janela do jogo.\n" +
      "• **Mostrar logs na aplicação**: exibe/esconde o painel de log no próprio Dashboard.\n" +
      "• **Mostrar marcações de região na tela do jogo**: liga/desliga de uma vez todos os retângulos verdes que marcam as regiões calibradas.\n\n" +
      "No rodapé: aviso de responsabilidade, status de Administrador e o card de sessão com a conta logada e o botão Sair da conta.",
  },
  {
    file: "02-settings.png",
    caption:
      "**2. Tela de Configurações (Settings)**\n\n" +
      "Fica atrás do item CONFIGS/PRESETS na barra lateral. Três blocos:\n\n" +
      "• **Hotkeys globais**: tecla de Pausar/Retomar e a de Parar tudo (funcionam mesmo sem foco no EasyF, se \"ativas\" estiver marcado). Aplicar salva a combinação; Parar tudo agora interrompe tudo na hora.\n" +
      "• **Modo background**: envia cliques/teclas direto pra janela do jogo via PostMessage, sem mover o cursor real - dá pra usar o PC normalmente com os módulos rodando. Atenção: alguns clients (ex: Miracle) leem a posição real do cursor do sistema, então mexer o mouse dentro do jogo enquanto um módulo clica pode dar clique errado (inclusive arrastar/usar item sem querer) - evite usar o mouse no jogo com módulos ativos. Tem também Selecionar janela do jogo... e Testar clique em background....\n" +
      "• **Perfis**: salva toda a config atual (abas, hotkeys, modo background) num perfil nomeado, carrega perfil salvo (pede reinício) e exporta/importa perfis como arquivo .json pra compartilhar ou backup.",
  },
  {
    file: "03-logs.png",
    caption:
      "**3. Logs**\n\n" +
      "Mostra o histórico completo de mensagens da sessão atual, independente do overlay sobre o jogo. Tem campo de busca pra filtrar por texto e botão Limpar pra esvaziar o histórico.",
  },
  {
    file: "04-about.png",
    caption:
      "**4. Sobre**\n\n" +
      "Tela simples com o nome do app, a versão instalada e o aviso de responsabilidade sobre o uso de automação.",
  },
  {
    file: "05-target-config.png",
    caption:
      "**5. Configurando o módulo Target**\n\n" +
      "Ataca automaticamente a criatura selecionada na Battle List, lendo a tela do jogo (sem API). Seções:\n" +
      "• **1. Battle List**: captura da região da Battle List e um modelo de \"lista vazia\" (recorte do cabeçalho + primeira linha sem monstro), usado pra detectar quando não há alvo.\n" +
      "• **2. Cor de ataque**: cor RGB (padrão vermelho puro 254,0,0) que aparece no nome da criatura em modo de ataque, com tolerância por canal e quantidade mínima de pixels.\n" +
      "• **3. Tecla de ataque**: hotkey configurada no próprio Tibia (Options > Hotkeys > Attack) que o Target aperta repetidamente, e o delay antes de conferir a cor de ataque.\n" +
      "• **4. Ritmo**: intervalos mínimo/máximo entre tentativas (lista vazia e já engajado) - variar deixa menos robótico.\n\n" +
      "O card do Target no Dashboard também tem Testar leitura da Battle List e Testar tecla de ataque, pra verificação pontual sem iniciar o módulo completo.",
  },
  {
    file: "06-cavebot-config.png",
    caption:
      "**6. Configurando o módulo Cavebot**\n\n" +
      "Anda automaticamente por uma rota de pontos marcados no mini mapa. Seções:\n" +
      "• **1. Mini mapa**: captura da região do mini mapa, base do reconhecimento de cada marcador da rota.\n" +
      "• **2. Rota**: lista ordenada de waypoints. Cada ponto associa um ícone de marcador real do mini mapa (arquivos 1.png a 15.png, na escala exata do jogo), tempo de espera após o clique e uma confiança mínima própria (ou a padrão). Botões pra adicionar, editar, remover e reordenar pontos.\n" +
      "• **3. Detecção e clique**: confiança padrão de reconhecimento, intervalo entre tentativas, tempo máximo de busca, falhas seguidas antes de pular pro próximo ponto, e jitter aplicado ao clique.\n\n" +
      "Aviso na tela: o Cavebot não lê a Battle List sozinho (rode o Target junto pra pausar a rota em combate) e esta versão não recolhe loot durante a rota (isso é papel do AutoLoot).",
  },
  {
    file: "07-autoloot-config.png",
    caption:
      "**7. Configurando o módulo AutoLoot**\n\n" +
      "Abre os corpos ao redor do personagem (os 8 SQMs adjacentes) assim que o Target confirma que a Battle List ficou vazia, e recolhe os itens configurados. Seções:\n" +
      "• **1. Posição do personagem**: ponto na tela onde o personagem fica parado, e o tamanho em pixels de 1 SQM - usado pra calcular os 8 SQMs ao redor.\n" +
      "• **2. Bag de origem (corpo)**: região onde a bag do corpo aberto aparece na tela.\n" +
      "• **3. Bag de destino**: ponto de destino pra onde os itens encontrados são arrastados.\n" +
      "• **4. Itens de loot**: itens reconhecidos por ícone (capturado manualmente ou via predefinições prontas de \"Moeda de ouro\" e \"White Mushroom\", já embutidas no programa).\n" +
      "• **5. Ritmo e limites**: espera após abrir cada corpo, intervalo de checagem, tempo máximo procurando item por passada, número de passadas por corpo, variação do clique/arraste e tentativas antes de avisar item preso ou bag de destino cheia.",
  },
  {
    file: "08-fishing-config.png",
    caption:
      "**8. Configurando o módulo AutoFishing**\n\n" +
      "Pesca automaticamente clicando na vara sobre tiles de água detectadas na tela. Seções:\n" +
      "• **1. Vara de pescar**: posição do slot da vara no inventário.\n" +
      "• **2. Região monitorada (lago)**: área da tela onde o AutoFishing procura água.\n" +
      "• **3. Detecção de água**: modo HSV (por cor) ou template (por imagem de referência), com calibração de cor, captura de template, área mínima, tamanho do SQM, cobertura mínima e recalibração automática pra compensar brilho dia/noite.\n" +
      "• **4. Clique e ritmo**: botão do mouse usado na água, delays mínimo/máximo entre lances, variação do clique, limite de lances e sortear entre as tiles encontradas.\n" +
      "• **5. Pausas periódicas (descanso)**: simula pausas de descanso após um tempo pescando, com duração variável, pra parecer mais natural.",
  },
  {
    file: "09-runemaker-config.png",
    caption:
      "**9. Configurando o módulo RuneMaker**\n\n" +
      "Cria runas (ou só treina mana, conjurando a magia sem gastar item). Seções:\n" +
      "• **1. Modo**: Criar runas ou ManaTraining (só conjura a magia, sem manipular item) - nunca os dois ao mesmo tempo.\n" +
      "• **2. Magia e blank runes**: hotkey da magia, quantidade de runas a criar (0 = até acabar a mana), slot da blank rune, e \"servidor não requer mão\" (aplica a magia direto no slot da blank rune, pulando segurar o item na mão), com os slots correspondentes.\n" +
      "• **2.1 Detecção de slot vazio**: templates de slot vazio (origem, mão, destino) pra confirmar cada etapa, com cobertura mínima configurável.\n" +
      "• **3. Limites de segurança (OCR)**: leitura da mana atual via OCR, com valor mínimo abaixo do qual o módulo pausa.\n" +
      "• **4. Ritmo**: delays mínimo/máximo entre lances e variação do clique.",
  },
  {
    file: "10-training-config.png",
    caption:
      "**10. Configurando o módulo Training**\n\n" +
      "Parecido com o Target, mas focado em treinar contra um monstro específico (ex: Training Monk), com extras de magia e anti-AFK:\n" +
      "• **1. Battle List** e **2. Cor de ataque**: mesma lógica do Target.\n" +
      "• **3. Tecla de ataque** e **4. Ritmo**: tecla configurada no jogo e delays entre tentativas.\n" +
      "• **5. Alvo de treino permanente**: nome do monstro de treino (lido via OCR na Battle List, tolerante a falhas), similaridade mínima do nome e tentativas antes de pausar se o alvo sumir da lista.\n" +
      "• **6. Magia de ataque (opcional)**: conjura uma magia de ataque junto com a tecla física, útil pra treinar magic level, com verificação de mana própria.\n\n" +
      "Há ainda a seção **7. Anti-AFK-kick** (mais abaixo na rolagem), que envia periodicamente um movimento leve (uma tecla e a oposta) pra evitar desconexão por inatividade.",
  },
  {
    file: "11-autofood.png",
    caption:
      "**11. Auto Food**\n\n" +
      "Diferente dos outros seis módulos, o Auto Food não tem tela de configuração própria - é ativado direto pelo checkbox \"Auto Food\" na seção Opções do Dashboard. Ao lado do checkbox aparece o estado atual do módulo (ex: \"parado\").",
  },
];

const outro =
  "**12. Fluxo básico de uso**\n\n" +
  "Um roteiro resumido pra começar a usar o EasyF do zero:\n\n" +
  "1. **Abra o app** rodando `python main.py` a partir da raiz do repositório (ou o executável instalado). Se pedir login, entre com sua conta.\n" +
  "2. **Configure o modo background** em Settings, se quiser continuar usando o PC normalmente com os módulos rodando - lembre do aviso sobre clients sensíveis à posição real do cursor (ex: Miracle) e evite mexer o mouse dentro do jogo com módulos ativos.\n" +
  "3. **Configure o Target primeiro**: capture a região da Battle List, o modelo de lista vazia e confirme a cor de ataque - a maioria dos outros módulos (Cavebot, Training, AutoLoot) depende do Target pra saber quando um combate começou ou terminou.\n" +
  "4. **Configure e ative os módulos que for usar** (Cavebot pra andar pela rota, AutoLoot pra recolher loot, AutoFishing/RuneMaker/Training conforme a necessidade), sempre calibrando as regiões/pontos com o jogo aberto na tela.\n" +
  "5. **Inicie os módulos** pelos botões Iniciar de cada cartão no Dashboard (ou pelas hotkeys globais configuradas em Settings).\n" +
  "6. **Monitore os Logs** (painel no Dashboard, overlay sobre o jogo, ou a tela de Logs) pra acompanhar o que está acontecendo e identificar rápido qualquer detecção que pare de funcionar (ex: depois de mudar o zoom ou o tamanho da janela do jogo, o que costuma quebrar calibrações visuais antigas).";

async function main() {
  await postText(
    "📖 **Tutorial completo do EasyF**\n\n" +
    "Guia passo a passo de todas as telas, módulos, botões e rotinas do app desktop - use como referência sempre que precisar configurar algo. Segue abaixo em partes, uma por tela/módulo."
  );
  await sleep(1200);

  for (const s of sections) {
    await postImage(s.file, s.caption);
    await sleep(1200);
  }

  await postText(outro);
  console.log("Tutorial completo postado.");
}

main();
