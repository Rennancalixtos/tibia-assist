import { MercadoPagoConfig, Preference, Payment } from "mercadopago";
import { supabaseAdmin } from "./supabase";

/**
 * Cliente Mercado Pago configurado com o access token do servidor.
 */
export const mercadoPagoClient = new MercadoPagoConfig({
  accessToken: process.env.MERCADOPAGO_ACCESS_TOKEN as string,
});

export type CheckoutResult = { url: string } | { error: string };

type PlanRow = {
  plan_id: string;
  days: number;
  price_cents: number;
  active: boolean;
};

/**
 * Base URL publica do backend, usada para montar `notification_url` e
 * `back_urls`. Nao ha variavel de ambiente dedicada para isso ainda (nao
 * podemos editar .env.example nesta tarefa) - em producao na Vercel a
 * plataforma sempre define VERCEL_URL automaticamente; localmente cai para
 * localhost (o Mercado Pago so precisa alcancar o webhook em producao).
 */
function resolveBaseUrl(): string {
  if (process.env.VERCEL_URL) {
    return `https://${process.env.VERCEL_URL}`;
  }
  return "http://localhost:3000";
}

/**
 * Cria uma preferencia de pagamento no Mercado Pago para `planId`, sempre
 * resolvendo dias/preco a partir da tabela `plans` no banco - nunca a partir
 * de dado enviado pelo cliente/bot do Discord. `external_reference` carrega
 * `userId:planId` para o webhook identificar quem pagou o que sem depender
 * de nada vindo do client no momento da confirmacao.
 */
export async function createCheckoutForUser(userId: string, planId: string): Promise<CheckoutResult> {
  const { data: plan, error } = await supabaseAdmin
    .from("plans")
    .select("plan_id, days, price_cents, active")
    .eq("plan_id", planId)
    .maybeSingle();

  if (error || !plan) {
    return { error: "Plano invalido." };
  }

  const row = plan as PlanRow;

  if (!row.active) {
    return { error: "Este plano nao esta disponivel no momento." };
  }

  const baseUrl = resolveBaseUrl();

  const preference = new Preference(mercadoPagoClient);
  const result = await preference.create({
    body: {
      items: [
        {
          id: row.plan_id,
          title: `Licenca EasyF - ${row.days} dias`,
          quantity: 1,
          unit_price: row.price_cents / 100,
          currency_id: "BRL",
        },
      ],
      external_reference: `${userId}:${row.plan_id}`,
      back_urls: {
        success: `${baseUrl}/`,
        failure: `${baseUrl}/`,
        pending: `${baseUrl}/`,
      },
      notification_url: `${baseUrl}/api/mercadopago/webhook`,
      // So aceita Pix (bank_transfer) mesmo neste checkout por link legado -
      // "Dinheiro em conta" nao pode ser excluido pela API, mas nao e um
      // meio de pagamento externo entao nao representa o mesmo risco.
      payment_methods: {
        excluded_payment_types: [
          { id: "credit_card" },
          { id: "debit_card" },
          { id: "prepaid_card" },
          { id: "ticket" },
          { id: "atm" },
        ],
      },
    },
  });

  const url = result.init_point;

  if (!url) {
    return { error: "Nao foi possivel gerar o link de pagamento." };
  }

  return { url };
}

export type PixResult =
  | {
      paymentId: string;
      qrCodeText: string;
      qrCodeBase64: string;
      expiresAt: string | null;
    }
  | { error: string };

/**
 * Cria um pagamento PIX direto (sem link de checkout, sem outras formas de
 * pagamento) via API de Payments do Mercado Pago - retorna o QR code (imagem
 * base64 + codigo copia-e-cola) pra exibir direto no Discord. Dias/preco
 * sempre vem da tabela `plans`, nunca do client/bot. `external_reference`
 * carrega `userId:planId:discordUserId` para o webhook confirmar a licenca E
 * avisar a pessoa certa por DM, sem depender de nada vindo do client no
 * momento da confirmacao.
 */
const PIX_EXPIRATION_MINUTES = 15;

export async function createPixPaymentForUser(
  userId: string,
  planId: string,
  email: string,
  discordUserId: string
): Promise<PixResult> {
  const { data: plan, error } = await supabaseAdmin
    .from("plans")
    .select("plan_id, days, price_cents, active")
    .eq("plan_id", planId)
    .maybeSingle();

  if (error || !plan) {
    return { error: "Plano invalido." };
  }

  const row = plan as PlanRow;

  if (!row.active) {
    return { error: "Este plano nao esta disponivel no momento." };
  }

  const baseUrl = resolveBaseUrl();
  const payment = new Payment(mercadoPagoClient);

  let result;
  try {
    result = await payment.create({
      body: {
        transaction_amount: row.price_cents / 100,
        description: `Licenca EasyF - ${row.days} dias`,
        payment_method_id: "pix",
        payer: { email },
        external_reference: `${userId}:${row.plan_id}:${discordUserId}`,
        notification_url: `${baseUrl}/api/mercadopago/webhook`,
        date_of_expiration: new Date(Date.now() + PIX_EXPIRATION_MINUTES * 60_000).toISOString(),
      },
    });
  } catch (err) {
    console.error("Falha ao criar pagamento PIX no Mercado Pago", err);
    return { error: "Nao foi possivel gerar o pagamento PIX. Tente novamente mais tarde." };
  }

  const transactionData = result.point_of_interaction?.transaction_data;

  if (!result.id || !transactionData?.qr_code || !transactionData?.qr_code_base64) {
    console.error("Resposta do Mercado Pago sem dados de QR code PIX", result.id, result.status);
    return { error: "O Mercado Pago nao retornou o QR code PIX. Tente novamente mais tarde." };
  }

  return {
    paymentId: String(result.id),
    qrCodeText: transactionData.qr_code,
    qrCodeBase64: transactionData.qr_code_base64,
    expiresAt: result.date_of_expiration ?? null,
  };
}
