import "dotenv/config";

const { DISCORD_APPLICATION_ID, DISCORD_BOT_TOKEN, DISCORD_GUILD_ID } = process.env;

if (!DISCORD_APPLICATION_ID || !DISCORD_BOT_TOKEN) {
  console.error("Defina DISCORD_APPLICATION_ID e DISCORD_BOT_TOKEN antes de rodar este script.");
  process.exit(1);
}

const commands = [
  {
    name: "teste-gratis",
    description: "Solicita um periodo de teste gratis do EasyF (aprovacao manual).",
  },
  {
    name: "comprar-licenca",
    description: "Compra uma licenca do EasyF via Mercado Pago.",
    options: [
      {
        type: 3,
        name: "plano",
        description: "Duracao da licenca",
        required: true,
        choices: [
          { name: "7 dias", value: "7" },
          { name: "15 dias", value: "15" },
          { name: "30 dias", value: "30" },
        ],
      },
    ],
  },
];

// Registro por guild (instantaneo) quando DISCORD_GUILD_ID esta definido -
// use isso em desenvolvimento. Sem essa variavel, registra globalmente
// (propagacao pode levar ate 1h no Discord).
const path = DISCORD_GUILD_ID
  ? `/applications/${DISCORD_APPLICATION_ID}/guilds/${DISCORD_GUILD_ID}/commands`
  : `/applications/${DISCORD_APPLICATION_ID}/commands`;

const response = await fetch(`https://discord.com/api/v10${path}`, {
  method: "PUT",
  headers: {
    Authorization: `Bot ${DISCORD_BOT_TOKEN}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify(commands),
});

if (!response.ok) {
  console.error(`Falha ao registrar comandos (${response.status}):`, await response.text());
  process.exit(1);
}

console.log(`Comandos registrados com sucesso${DISCORD_GUILD_ID ? ` na guild ${DISCORD_GUILD_ID}` : " globalmente"}.`);
