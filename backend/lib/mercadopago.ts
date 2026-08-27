import { MercadoPagoConfig, Preference } from "mercadopago";
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
    },
  });

  const url = result.init_point;

  if (!url) {
    return { error: "Nao foi possivel gerar o link de pagamento." };
  }

  return { url };
}
