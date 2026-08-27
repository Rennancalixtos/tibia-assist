import {
  InteractionResponseType,
  discordApi,
  emailModal,
  ephemeralReply,
  modalSubmitValue,
} from "@/lib/discord/core";
import { resolveAccountByEmail } from "@/lib/discord/account-link";
import { supabaseAdmin } from "@/lib/supabase";

export const TRIAL_COMMAND_NAME = "teste-gratis";

const REQUEST_EMAIL_MODAL_ID = "trial:request-email";

function extractDiscordUserId(interaction: any): string | undefined {
  return interaction?.member?.user?.id ?? interaction?.user?.id;
}

function updateMessageResponse(content: string) {
  return {
    type: InteractionResponseType.UPDATE_MESSAGE,
    data: {
      content,
      components: [],
    },
  };
}

/**
 * Envia uma DM ao usuario avisando da decisao (aprovado/rejeitado). Best
 * effort: usuarios que bloqueiam DM de membros do servidor ou que ja
 * deixaram o servidor fazem essa chamada falhar - nunca deve derrubar o
 * fluxo de aprovacao/rejeicao por causa disso.
 */
async function sendTrialDecisionDm(discordUserId: string, content: string): Promise<void> {
  try {
    const dmChannelResponse = await discordApi("/users/@me/channels", {
      method: "POST",
      body: JSON.stringify({ recipient_id: discordUserId }),
    });
    if (!dmChannelResponse.ok) {
      return;
    }
    const dmChannel = await dmChannelResponse.json();
    await discordApi(`/channels/${dmChannel.id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
  } catch (err) {
    console.error("Falha ao enviar DM de decisao de teste gratis", err);
  }
}

export async function handleTrialCommand(_interaction: any) {
  return emailModal(REQUEST_EMAIL_MODAL_ID, "Solicitar teste gratis", "Seu e-mail cadastrado no EasyF");
}

export async function handleTrialModalSubmit(interaction: any) {
  if (interaction?.data?.custom_id !== REQUEST_EMAIL_MODAL_ID) {
    return ephemeralReply("Formulario de teste gratis desconhecido.");
  }

  const email = modalSubmitValue(interaction, "email");
  const discordUserId = extractDiscordUserId(interaction);

  if (!discordUserId) {
    return ephemeralReply("Nao foi possivel identificar seu usuario do Discord. Tente novamente.");
  }

  const account = await resolveAccountByEmail(email);
  if (!account) {
    return ephemeralReply(
      "Nao encontramos nenhuma conta cadastrada com esse e-mail no EasyF. Baixe o app e crie sua conta antes de solicitar o teste gratis."
    );
  }

  const { data: inserted, error } = await supabaseAdmin
    .from("trial_requests")
    .insert({
      user_id: account.userId,
      discord_user_id: discordUserId,
      status: "pending",
    })
    .select("id")
    .single();

  if (error) {
    if (error.code === "23505") {
      return ephemeralReply("Voce ja solicitou um teste gratis antes. Aguarde a analise da sua solicitacao.");
    }
    console.error("Falha ao criar solicitacao de teste gratis", error);
    return ephemeralReply("Falha ao registrar sua solicitacao de teste gratis. Tente novamente mais tarde.");
  }

  const trialChannelId = process.env.DISCORD_TRIAL_CHANNEL_ID;
  if (!trialChannelId) {
    console.error("DISCORD_TRIAL_CHANNEL_ID nao configurado - solicitacao criada sem notificacao no canal");
  } else {
    try {
      await discordApi(`/channels/${trialChannelId}/messages`, {
        method: "POST",
        body: JSON.stringify({
          embeds: [
            {
              title: "Nova solicitacao de teste gratis",
              color: 0x5865f2,
              fields: [
                { name: "E-mail", value: account.email, inline: true },
                { name: "Discord", value: `<@${discordUserId}>`, inline: true },
              ],
              footer: { text: `ID da solicitacao: ${inserted.id}` },
            },
          ],
          components: [
            {
              type: 1,
              components: [
                {
                  type: 2,
                  style: 3,
                  label: "Aprovar",
                  custom_id: `trial:approve:${inserted.id}`,
                },
                {
                  type: 2,
                  style: 4,
                  label: "Rejeitar",
                  custom_id: `trial:reject:${inserted.id}`,
                },
              ],
            },
          ],
        }),
      });
    } catch (err) {
      console.error("Falha ao postar solicitacao de teste gratis no canal de aprovacao", err);
    }
  }

  return ephemeralReply(
    "Seu pedido de teste gratis foi enviado para aprovacao. Voce recebera uma mensagem direta (DM) assim que houver uma decisao."
  );
}

export async function handleTrialComponent(interaction: any, customId: string) {
  const parts = customId.split(":");
  const action = parts[1];
  const requestId = parts[2];

  if ((action !== "approve" && action !== "reject") || !requestId) {
    return ephemeralReply("Acao de teste gratis desconhecida.");
  }

  const adminRoleId = process.env.DISCORD_ADMIN_ROLE_ID;
  const memberRoles: string[] = interaction?.member?.roles ?? [];
  if (!adminRoleId || !memberRoles.includes(adminRoleId)) {
    return ephemeralReply("Voce nao tem permissao para aprovar ou rejeitar solicitacoes de teste gratis.");
  }

  const { data: trialRequest, error: fetchError } = await supabaseAdmin
    .from("trial_requests")
    .select("id, user_id, discord_user_id, status")
    .eq("id", requestId)
    .maybeSingle();

  if (fetchError || !trialRequest) {
    return ephemeralReply("Solicitacao de teste gratis nao encontrada.");
  }

  if (trialRequest.status !== "pending") {
    return ephemeralReply("Essa solicitacao ja foi decidida por outra pessoa.");
  }

  const clickerId = extractDiscordUserId(interaction);
  const decidedAt = new Date().toISOString();

  if (action === "approve") {
    const hoursGranted = Number(process.env.DEFAULT_TRIAL_HOURS ?? 48);

    const { error: updateError, count } = await supabaseAdmin
      .from("trial_requests")
      .update(
        {
          status: "approved",
          decided_at: decidedAt,
          decided_by_discord_id: clickerId,
          hours_granted: hoursGranted,
        },
        { count: "exact" }
      )
      .eq("id", requestId)
      .eq("status", "pending");

    if (updateError || !count) {
      return ephemeralReply("Essa solicitacao ja foi decidida por outra pessoa.");
    }

    const currentPeriodEnd = new Date(Date.now() + hoursGranted * 60 * 60 * 1000).toISOString();

    const { error: upsertError } = await supabaseAdmin.from("licenses").upsert(
      {
        user_id: trialRequest.user_id,
        status: "active",
        current_period_end: currentPeriodEnd,
        plan_type: "trial",
        payment_provider: null,
      },
      { onConflict: "user_id" }
    );

    if (upsertError) {
      console.error("Falha ao ativar licenca de teste gratis", upsertError);
      return ephemeralReply(
        "Solicitacao marcada como aprovada, mas houve falha ao ativar a licenca. Verifique manualmente."
      );
    }

    await sendTrialDecisionDm(
      trialRequest.discord_user_id,
      `Seu teste gratis do EasyF foi aprovado! Voce tem ${hoursGranted} horas de acesso a partir de agora.`
    );

    return updateMessageResponse(`Aprovado por <@${clickerId}>.`);
  }

  const { error: rejectError, count: rejectCount } = await supabaseAdmin
    .from("trial_requests")
    .update(
      {
        status: "rejected",
        decided_at: decidedAt,
        decided_by_discord_id: clickerId,
      },
      { count: "exact" }
    )
    .eq("id", requestId)
    .eq("status", "pending");

  if (rejectError || !rejectCount) {
    return ephemeralReply("Essa solicitacao ja foi decidida por outra pessoa.");
  }

  await sendTrialDecisionDm(trialRequest.discord_user_id, "Seu pedido de teste gratis no EasyF foi rejeitado.");

  return updateMessageResponse(`Rejeitado por <@${clickerId}>.`);
}
