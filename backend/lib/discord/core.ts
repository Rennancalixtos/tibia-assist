import nacl from "tweetnacl";

export const DISCORD_API_BASE = "https://discord.com/api/v10";

export const InteractionType = {
  PING: 1,
  APPLICATION_COMMAND: 2,
  MESSAGE_COMPONENT: 3,
  MODAL_SUBMIT: 5,
} as const;

export const InteractionResponseType = {
  PONG: 1,
  CHANNEL_MESSAGE_WITH_SOURCE: 4,
  DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE: 5,
  DEFERRED_UPDATE_MESSAGE: 6,
  UPDATE_MESSAGE: 7,
  MODAL: 9,
} as const;

export const MessageFlags = {
  EPHEMERAL: 1 << 6,
} as const;

export function verifyDiscordRequest(rawBody: string, signature: string | null, timestamp: string | null): boolean {
  const publicKey = process.env.DISCORD_PUBLIC_KEY;
  if (!signature || !timestamp || !publicKey) {
    return false;
  }
  try {
    return nacl.sign.detached.verify(
      Buffer.from(timestamp + rawBody),
      Buffer.from(signature, "hex"),
      Buffer.from(publicKey, "hex")
    );
  } catch {
    return false;
  }
}

function botHeaders(): Record<string, string> {
  return {
    Authorization: `Bot ${process.env.DISCORD_BOT_TOKEN}`,
    "Content-Type": "application/json",
  };
}

export async function discordApi(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${DISCORD_API_BASE}${path}`, {
    ...init,
    headers: { ...botHeaders(), ...(init.headers ?? {}) },
  });
}

export function ephemeralReply(content: string) {
  return {
    type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
    data: { content, flags: MessageFlags.EPHEMERAL },
  };
}

export function emailModal(customId: string, title: string, label: string) {
  return {
    type: InteractionResponseType.MODAL,
    data: {
      custom_id: customId,
      title,
      components: [
        {
          type: 1,
          components: [
            {
              type: 4,
              custom_id: "email",
              style: 1,
              label,
              placeholder: "seuemail@exemplo.com",
              required: true,
              min_length: 5,
              max_length: 254,
            },
          ],
        },
      ],
    },
  };
}

export function modalSubmitValue(interaction: any, customId: string): string {
  const row = interaction?.data?.components?.[0];
  const component = row?.components?.find((c: any) => c.custom_id === customId);
  return String(component?.value ?? "").trim();
}
