import { NextResponse } from "next/server";
import crypto from "crypto";
import { Payment } from "mercadopago";
import { mercadoPagoClient } from "@/lib/mercadopago";
import { supabaseAdmin } from "@/lib/supabase";
import { editOriginalInteractionMessage } from "@/lib/discord/core";

export const dynamic = "force-dynamic";

/**
 * Valida a assinatura `x-signature` do Mercado Pago seguindo o formato
 * oficial: header no formato "ts=<timestamp>,v1=<hmac>", manifest
 * "id:<data.id>;request-id:<x-request-id>;ts:<ts>;" assinado em HMAC-SHA256
 * com MERCADOPAGO_WEBHOOK_SECRET. `data.id` vem da query string da propria
 * notificacao (nunca do corpo, que nao entra no manifest).
 */
function verifyMercadoPagoSignature(
  dataId: string,
  signatureHeader: string,
  requestId: string
): boolean {
  const secret = process.env.MERCADOPAGO_WEBHOOK_SECRET;
  if (!secret) {
    return false;
  }

  const parts: Record<string, string> = {};
  for (const chunk of signatureHeader.split(",")) {
    const [key, value] = chunk.trim().split("=");
    if (key && value) {
      parts[key] = value;
    }
  }

  const ts = parts.ts;
  const v1 = parts.v1;
  if (!ts || !v1) {
    return false;
  }

  const manifest = `id:${dataId.toLowerCase()};request-id:${requestId};ts:${ts};`;
  const expected = crypto.createHmac("sha256", secret).update(manifest).digest("hex");

  try {
    return crypto.timingSafeEqual(Buffer.from(expected, "hex"), Buffer.from(v1, "hex"));
  } catch {
    return false;
  }
}

export async function POST(request: Request) {
  const url = new URL(request.url);
  const dataId = url.searchParams.get("data.id") ?? url.searchParams.get("id");
  const signatureHeader = request.headers.get("x-signature");
  const requestId = request.headers.get("x-request-id");

  if (!dataId || !signatureHeader || !requestId) {
    return NextResponse.json({ error: "Notificacao invalida." }, { status: 400 });
  }

  if (!verifyMercadoPagoSignature(dataId, signatureHeader, requestId)) {
    return NextResponse.json({ error: "Assinatura invalida." }, { status: 401 });
  }

  const payment = await new Payment(mercadoPagoClient).get({ id: dataId });

  if (payment.status !== "approved") {
    return NextResponse.json({ received: true });
  }

  // Formato "userId:planId" (checkout por link, legado) ou
  // "userId:planId:discordUserId" (fluxo atual PIX via Discord - o terceiro
  // campo nao e mais usado aqui, so foi necessario historicamente pra DM;
  // a confirmacao hoje e so via edicao da mensagem original, usando o
  // interaction_token guardado em mercadopago_payments).
  const externalReference = payment.external_reference ?? "";
  const [userId, planId] = externalReference.split(":");

  if (!userId || !planId) {
    console.error("Pagamento aprovado sem external_reference valido", payment.id);
    return NextResponse.json({ received: true });
  }

  const paymentId = String(payment.id);

  // A linha pode ja existir (inserida com status 'pending' na hora de criar
  // o PIX, carregando o interaction_token) ou nao (fluxo legado de checkout
  // por link, que nunca insere antecipadamente) - trata os dois casos.
  const { data: existingPayment } = await supabaseAdmin
    .from("mercadopago_payments")
    .select("status, interaction_token")
    .eq("payment_id", paymentId)
    .maybeSingle();

  let interactionToken: string | null = null;

  if (existingPayment) {
    if (existingPayment.status === "processed") {
      return NextResponse.json({ received: true });
    }
    interactionToken = existingPayment.interaction_token;
    const { error: updateError, count } = await supabaseAdmin
      .from("mercadopago_payments")
      .update({ status: "processed" }, { count: "exact" })
      .eq("payment_id", paymentId)
      .eq("status", "pending");

    if (updateError || !count) {
      return NextResponse.json({ received: true });
    }
  } else {
    const { error: insertError } = await supabaseAdmin
      .from("mercadopago_payments")
      .insert({ payment_id: paymentId, user_id: userId, plan_id: planId, status: "processed" });

    if (insertError) {
      if (insertError.code === "23505") {
        return NextResponse.json({ received: true });
      }
      console.error("Falha ao registrar pagamento do Mercado Pago", insertError);
      return NextResponse.json({ error: "Falha ao registrar pagamento." }, { status: 500 });
    }
  }

  const { data: plan, error: planError } = await supabaseAdmin
    .from("plans")
    .select("days")
    .eq("plan_id", planId)
    .maybeSingle();

  if (planError || !plan) {
    console.error("Plano nao encontrado ao processar pagamento aprovado", planId);
    return NextResponse.json({ received: true });
  }

  const currentPeriodEnd = new Date(Date.now() + plan.days * 24 * 60 * 60 * 1000).toISOString();

  const { error: upsertError } = await supabaseAdmin.from("licenses").upsert(
    {
      user_id: userId,
      status: "active",
      current_period_end: currentPeriodEnd,
      plan_type: "paid",
      payment_provider: "mercadopago",
    },
    { onConflict: "user_id" }
  );

  if (upsertError) {
    console.error("Falha ao gravar licenca (webhook Mercado Pago)", upsertError);
    return NextResponse.json({ error: "Falha ao gravar licenca." }, { status: 500 });
  }

  // Edita a propria mensagem do QR code no chat - so funciona dentro de ate
  // 15min da interacao original (limite do Discord para este endpoint).
  // Passado esse prazo, so loga o erro - nunca cai pra DM (decisao do
  // produto: jamais mandar DM pro usuario final).
  if (interactionToken) {
    await editOriginalInteractionMessage(interactionToken, {
      content: `Pagamento confirmado! Sua licenca do EasyF de ${plan.days} dias foi ativada.`,
      embeds: [],
      components: [],
      attachments: [],
    });
  }

  return NextResponse.json({ received: true });
}
