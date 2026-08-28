import { discordApi, ephemeralReply } from "@/lib/discord/core";
import { supabaseAdmin } from "@/lib/supabase";

const VIEW_CHANNEL = 1 << 10;
const SEND_MESSAGES = 1 << 11;

function extractDiscordUserId(interaction: any): string | undefined {
  return interaction?.member?.user?.id ?? interaction?.user?.id;
}

function slugifyUsername(interaction: any): string {
  const user = interaction?.member?.user ?? interaction?.user ?? {};
  const raw = String(user.username ?? user.global_name ?? "user").toLowerCase();
  const slug = raw.replace(/[^a-z0-9]/g, "").slice(0, 20);
  return slug || "user";
}

async function openTicket(interaction: any) {
  const discordUserId = extractDiscordUserId(interaction);
  if (!discordUserId) {
    return ephemeralReply("Nao foi possivel identificar seu usuario do Discord. Tente novamente.");
  }

  const { data: existing } = await supabaseAdmin
    .from("support_tickets")
    .select("channel_id")
    .eq("discord_user_id", discordUserId)
    .eq("status", "open")
    .maybeSingle();

  if (existing) {
    return ephemeralReply(`Voce ja tem um ticket aberto: <#${existing.channel_id}>`);
  }

  const guildId = process.env.DISCORD_GUILD_ID;
  const adminRoleId = process.env.DISCORD_ADMIN_ROLE_ID;
  const categoryId = process.env.DISCORD_TICKET_CATEGORY_ID;

  if (!guildId || !adminRoleId) {
    return ephemeralReply("Sistema de ticket nao configurado corretamente. Avise um administrador.");
  }

  const createResponse = await discordApi(`/guilds/${guildId}/channels`, {
    method: "POST",
    body: JSON.stringify({
      name: `ticket-${slugifyUsername(interaction)}`,
      type: 0,
      parent_id: categoryId || undefined,
      permission_overwrites: [
        { id: guildId, type: 0, deny: String(VIEW_CHANNEL) },
        { id: discordUserId, type: 1, allow: String(VIEW_CHANNEL | SEND_MESSAGES) },
        { id: adminRoleId, type: 0, allow: String(VIEW_CHANNEL | SEND_MESSAGES) },
      ],
    }),
  });

  if (!createResponse.ok) {
    console.error("Falha ao criar canal de ticket", await createResponse.text());
    return ephemeralReply(
      "Nao foi possivel abrir o ticket. Confirme se o bot tem a permissao 'Gerenciar Canais' no servidor."
    );
  }

  const channel = await createResponse.json();

  const { error: insertError } = await supabaseAdmin.from("support_tickets").insert({
    channel_id: channel.id,
    discord_user_id: discordUserId,
    status: "open",
  });

  if (insertError) {
    console.error("Falha ao registrar ticket no banco", insertError);
  }

  await discordApi(`/channels/${channel.id}/messages`, {
    method: "POST",
    body: JSON.stringify({
      content: `Ticket aberto por <@${discordUserId}>. Descreva seu problema, um admin vai te atender em breve.`,
      components: [
        {
          type: 1,
          components: [{ type: 2, style: 4, label: "Fechar Ticket", custom_id: "ticket:close" }],
        },
      ],
    }),
  });

  return ephemeralReply(`Seu ticket foi criado: <#${channel.id}>`);
}

async function closeTicket(interaction: any) {
  const channelId = interaction?.channel_id ?? interaction?.channel?.id;
  if (!channelId) {
    return ephemeralReply("Nao foi possivel identificar o canal do ticket.");
  }

  const clickerId = extractDiscordUserId(interaction);
  const adminRoleId = process.env.DISCORD_ADMIN_ROLE_ID;
  const memberRoles: string[] = interaction?.member?.roles ?? [];

  const { data: ticket } = await supabaseAdmin
    .from("support_tickets")
    .select("discord_user_id")
    .eq("channel_id", channelId)
    .maybeSingle();

  const isOwner = ticket?.discord_user_id === clickerId;
  const isAdmin = !!adminRoleId && memberRoles.includes(adminRoleId);

  if (!isOwner && !isAdmin) {
    return ephemeralReply("Voce nao tem permissao para fechar este ticket.");
  }

  await supabaseAdmin
    .from("support_tickets")
    .update({ status: "closed", closed_at: new Date().toISOString() })
    .eq("channel_id", channelId);

  await discordApi(`/channels/${channelId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content: "Ticket encerrado. Este canal sera apagado em instantes." }),
  });

  try {
    await discordApi(`/channels/${channelId}`, { method: "DELETE" });
  } catch (err) {
    console.error("Falha ao apagar canal de ticket", err);
  }

  return ephemeralReply("Ticket fechado.");
}

export async function handleTicketComponent(interaction: any, customId: string) {
  if (customId === "ticket:open") {
    return openTicket(interaction);
  }
  if (customId === "ticket:close") {
    return closeTicket(interaction);
  }
  return ephemeralReply("Acao de ticket desconhecida.");
}
