import "dotenv/config";

const { DISCORD_BOT_TOKEN, DISCORD_PANEL_CHANNEL_ID } = process.env;

if (!DISCORD_BOT_TOKEN || !DISCORD_PANEL_CHANNEL_ID) {
  console.error("Defina DISCORD_BOT_TOKEN e DISCORD_PANEL_CHANNEL_ID antes de rodar este script.");
  process.exit(1);
}

const payload = {
  embeds: [
    {
      title: "EasyF - Teste gratis e licencas",
      description:
        "Clique num dos botoes abaixo. Voce vai precisar informar o e-mail da sua conta no EasyF.",
      color: 5793266,
    },
  ],
  components: [
    {
      type: 1,
      components: [{ type: 2, style: 3, label: "Testar Gratis", custom_id: "trial:open-modal" }],
    },
    {
      type: 1,
      components: [
        { type: 2, style: 1, label: "Comprar 7 dias", custom_id: "purchase:open-modal:7d" },
        { type: 2, style: 1, label: "Comprar 15 dias", custom_id: "purchase:open-modal:15d" },
        { type: 2, style: 1, label: "Comprar 30 dias", custom_id: "purchase:open-modal:30d" },
      ],
    },
  ],
};

const response = await fetch(`https://discord.com/api/v10/channels/${DISCORD_PANEL_CHANNEL_ID}/messages`, {
  method: "POST",
  headers: {
    Authorization: `Bot ${DISCORD_BOT_TOKEN}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify(payload),
});

if (!response.ok) {
  console.error(`Falha ao publicar o painel (${response.status}):`, await response.text());
  process.exit(1);
}

console.log("Painel publicado com sucesso.");
