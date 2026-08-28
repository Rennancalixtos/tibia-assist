import "dotenv/config";

const [, , channelId, title, url] = process.argv;
const { DISCORD_BOT_TOKEN } = process.env;

if (!DISCORD_BOT_TOKEN || !channelId || !title || !url) {
  console.error('Uso: node scripts/post-link-message.mjs <channelId> "<titulo>" <url>');
  process.exit(1);
}

const payload = {
  embeds: [{ title, description: url, color: 5793266 }],
  components: [
    {
      type: 1,
      components: [{ type: 2, style: 5, label: "Abrir link", url }],
    },
  ],
};

const response = await fetch(`https://discord.com/api/v10/channels/${channelId}/messages`, {
  method: "POST",
  headers: {
    Authorization: `Bot ${DISCORD_BOT_TOKEN}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify(payload),
});

if (!response.ok) {
  console.error(`Falha ao publicar a mensagem (${response.status}):`, await response.text());
  process.exit(1);
}

console.log("Mensagem publicada com sucesso.");
