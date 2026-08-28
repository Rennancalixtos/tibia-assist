import "dotenv/config";

const {
  DISCORD_BOT_TOKEN,
  DISCORD_TRIAL_PANEL_CHANNEL_ID,
  DISCORD_PURCHASE_PANEL_CHANNEL_ID,
  DISCORD_TICKET_CHANNEL_ID,
} = process.env;

if (
  !DISCORD_BOT_TOKEN ||
  !DISCORD_TRIAL_PANEL_CHANNEL_ID ||
  !DISCORD_PURCHASE_PANEL_CHANNEL_ID ||
  !DISCORD_TICKET_CHANNEL_ID
) {
  console.error(
    "Defina DISCORD_BOT_TOKEN, DISCORD_TRIAL_PANEL_CHANNEL_ID, DISCORD_PURCHASE_PANEL_CHANNEL_ID e DISCORD_TICKET_CHANNEL_ID antes de rodar este script."
  );
  process.exit(1);
}

async function postPanel(channelId, payload, label) {
  const response = await fetch(`https://discord.com/api/v10/channels/${channelId}/messages`, {
    method: "POST",
    headers: {
      Authorization: `Bot ${DISCORD_BOT_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    console.error(`Falha ao publicar o painel de ${label} (${response.status}):`, await response.text());
    process.exit(1);
  }

  console.log(`Painel de ${label} publicado com sucesso.`);
}

await postPanel(
  DISCORD_TRIAL_PANEL_CHANNEL_ID,
  {
    embeds: [
      {
        title: "Teste gratis - EasyF",
        description: "Clique no botao abaixo pra solicitar um periodo de teste gratis. Voce vai precisar informar o e-mail da sua conta no EasyF.",
        color: 5793266,
      },
    ],
    components: [
      {
        type: 1,
        components: [{ type: 2, style: 3, label: "Testar Gratis", custom_id: "trial:open-modal" }],
      },
    ],
  },
  "teste gratis"
);

await postPanel(
  DISCORD_PURCHASE_PANEL_CHANNEL_ID,
  {
    embeds: [
      {
        title: "Comprar licenca - EasyF",
        description: "Clique num dos planos abaixo pra comprar. Voce vai precisar informar o e-mail da sua conta no EasyF.",
        color: 5793266,
      },
    ],
    components: [
      {
        type: 1,
        components: [
          { type: 2, style: 1, label: "7 dias", custom_id: "purchase:open-modal:7d" },
          { type: 2, style: 1, label: "15 dias", custom_id: "purchase:open-modal:15d" },
          { type: 2, style: 1, label: "30 dias", custom_id: "purchase:open-modal:30d" },
        ],
      },
    ],
  },
  "compra"
);

await postPanel(
  DISCORD_TICKET_CHANNEL_ID,
  {
    embeds: [
      {
        title: "Suporte - EasyF",
        description: "Precisa de ajuda? Clique no botao abaixo pra abrir um ticket privado com o suporte.",
        color: 5793266,
      },
    ],
    components: [
      {
        type: 1,
        components: [{ type: 2, style: 1, label: "Abrir Ticket", custom_id: "ticket:open" }],
      },
    ],
  },
  "ticket"
);
