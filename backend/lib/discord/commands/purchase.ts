import { ephemeralReply, emailModal, modalSubmitValue } from "@/lib/discord/core";
import { resolveAccountByEmail } from "@/lib/discord/account-link";
import { createCheckoutForUser } from "@/lib/mercadopago";

export const PURCHASE_COMMAND_NAME = "comprar-licenca";

const MODAL_PREFIX = "purchase:request-email:";

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
 * recusa a compra sem criar nenhuma preferencia de pagamento.
 */
export async function handlePurchaseModalSubmit(interaction: any) {
  const customId: string = interaction?.data?.custom_id ?? "";
  const planId = customId.startsWith(MODAL_PREFIX) ? customId.slice(MODAL_PREFIX.length) : "";

  if (!planId) {
    return ephemeralReply("Nao foi possivel identificar o plano selecionado. Tente novamente.");
  }

  const email = modalSubmitValue(interaction, "email");

  const account = await resolveAccountByEmail(email);

  if (!account) {
    return ephemeralReply(
      "Nao encontramos nenhuma conta cadastrada com esse e-mail. Crie sua conta no aplicativo do EasyF antes de comprar uma licenca."
    );
  }

  const result = await createCheckoutForUser(account.userId, planId);

  if ("error" in result) {
    return ephemeralReply(`Nao foi possivel gerar o pagamento: ${result.error}`);
  }

  return ephemeralReply(
    `Tudo certo! Finalize o pagamento no link abaixo:\n${result.url}\n\nApos a confirmacao do pagamento, sua licenca sera ativada automaticamente.`
  );
}

export async function handlePurchaseComponent(_interaction: any, _customId: string) {
  return ephemeralReply("Nenhuma acao pendente.");
}
