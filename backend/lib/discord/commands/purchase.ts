import { ephemeralReply, ephemeralAttachmentReply, emailModal, modalSubmitValue } from "@/lib/discord/core";
import { resolveAccountByEmail } from "@/lib/discord/account-link";
import { createPixPaymentForUser } from "@/lib/mercadopago";

export const PURCHASE_COMMAND_NAME = "comprar-licenca";

const MODAL_PREFIX = "purchase:request-email:";

function extractDiscordUserId(interaction: any): string | undefined {
  return interaction?.member?.user?.id ?? interaction?.user?.id;
}

function formatExpiration(expiresAt: string | null): string {
  if (!expiresAt) {
    return "em alguns minutos";
  }
  try {
    const formatted = new Date(expiresAt).toLocaleString("pt-BR", {
      timeZone: "America/Sao_Paulo",
      hour: "2-digit",
      minute: "2-digit",
    });
    return `as ${formatted}`;
  } catch {
    return "em alguns minutos";
  }
}

export async function handlePurchaseCommand(interaction: any) {
  const dias = interaction?.data?.options?.find((option: any) => option.name === "plano")?.value;

  if (!dias) {
    return ephemeralReply("Selecione um plano valido antes de continuar.");
  }

  const planId = `${dias}d`;

  return emailModal(
    `${MODAL_PREFIX}${planId}`,
    "Comprar licenca",
    "Seu e-mail cadastrado no EasyF"
  );
}

/**
 * So chama o Mercado Pago DEPOIS de confirmar que o e-mail digitado
 * corresponde a uma conta ja cadastrada (auth.users) - se nao resolver,
 * recusa a compra sem criar nenhum pagamento. Pagamento e sempre PIX (unica
 * forma de pagamento aceita neste fluxo), com o QR code exibido direto na
 * mensagem ephemeral - sem link de checkout externo.
 */
export async function handlePurchaseModalSubmit(interaction: any) {
  const customId: string = interaction?.data?.custom_id ?? "";
  const planId = customId.startsWith(MODAL_PREFIX) ? customId.slice(MODAL_PREFIX.length) : "";

  if (!planId) {
    return ephemeralReply("Nao foi possivel identificar o plano selecionado. Tente novamente.");
  }

  const email = modalSubmitValue(interaction, "email");
  const discordUserId = extractDiscordUserId(interaction);

  if (!discordUserId) {
    return ephemeralReply("Nao foi possivel identificar seu usuario do Discord. Tente novamente.");
  }

  const account = await resolveAccountByEmail(email);

  if (!account) {
    return ephemeralReply(
      "Nao encontramos nenhuma conta cadastrada com esse e-mail. Crie sua conta no aplicativo do EasyF antes de comprar uma licenca."
    );
  }

  const result = await createPixPaymentForUser(account.userId, planId, account.email, discordUserId);

  if ("error" in result) {
    return ephemeralReply(`Nao foi possivel gerar o pagamento: ${result.error}`);
  }

  return ephemeralAttachmentReply(
    `Escaneie o QR code abaixo com o app do seu banco, ou copie o codigo:\n\`\`\`${result.qrCodeText}\`\`\`\nEsse PIX expira ${formatExpiration(result.expiresAt)}. Assim que o pagamento for confirmado, sua licenca e ativada automaticamente e voce recebe uma DM avisando.`,
    [{ title: "Pagamento PIX - EasyF", color: 5793266, image: { url: "attachment://pix-qrcode.png" } }],
    "pix-qrcode.png",
    result.qrCodeBase64
  );
}

const PANEL_BUTTON_PREFIX = "purchase:open-modal:";

export async function handlePurchaseComponent(_interaction: any, customId: string) {
  if (customId.startsWith(PANEL_BUTTON_PREFIX)) {
    const planId = customId.slice(PANEL_BUTTON_PREFIX.length);
    return emailModal(`${MODAL_PREFIX}${planId}`, "Comprar licenca", "Seu e-mail cadastrado no EasyF");
  }
  return ephemeralReply("Nenhuma acao pendente.");
}
