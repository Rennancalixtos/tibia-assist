import "dotenv/config";
import { readFile } from "fs/promises";
import { basename } from "path";

const [, , channelId, imagePath, caption] = process.argv;
const { DISCORD_BOT_TOKEN } = process.env;

if (!DISCORD_BOT_TOKEN || !channelId || !imagePath || !caption) {
  console.error('Uso: node scripts/post-image-message.mjs <channelId> <caminhoDaImagem> "<legenda>"');
  process.exit(1);
}

const fileBuffer = await readFile(imagePath);
const fileName = basename(imagePath);
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

const response = await fetch(`https://discord.com/api/v10/channels/${channelId}/messages`, {
  method: "POST",
  headers: {
    Authorization: `Bot ${DISCORD_BOT_TOKEN}`,
    "Content-Type": `multipart/form-data; boundary=${boundary}`,
  },
  body: Buffer.concat(parts),
});

if (!response.ok) {
  console.error(`Falha ao publicar a imagem (${response.status}):`, await response.text());
  process.exit(1);
}

console.log(`Imagem "${fileName}" publicada com sucesso.`);
