import { NextResponse } from "next/server";
import { stripe } from "@/lib/stripe";
import { supabaseAdmin } from "@/lib/supabase";
import { buildLicense } from "@/lib/license";

export async function GET(request: Request) {
  const sessionId = new URL(request.url).searchParams.get("session_id");

  if (!sessionId) {
    return NextResponse.json({ error: "Informe session_id." }, { status: 400 });
  }

  let checkoutSession;
  try {
    checkoutSession = await stripe.checkout.sessions.retrieve(sessionId);
  } catch (err) {
    console.error("Falha ao buscar checkout session", err);
    return NextResponse.json({ error: "Sessao de checkout nao encontrada." }, { status: 400 });
  }

  const subscriptionId =
    typeof checkoutSession.subscription === "string"
      ? checkoutSession.subscription
      : checkoutSession.subscription?.id;

  const customerId =
    typeof checkoutSession.customer === "string"
      ? checkoutSession.customer
      : checkoutSession.customer?.id;

  let row = null;

  if (subscriptionId) {
    const { data } = await supabaseAdmin
      .from("licenses")
      .select("status, current_period_end")
      .eq("stripe_subscription_id", subscriptionId)
      .maybeSingle();
    row = data;
  }

  if (!row && customerId) {
    const { data } = await supabaseAdmin
      .from("licenses")
      .select("status, current_period_end")
      .eq("stripe_customer_id", customerId)
      .maybeSingle();
    row = data;
  }

  if (!row) {
    // O webhook ainda nao processou o evento - o frontend deve continuar tentando.
    return NextResponse.json({ ready: false }, { status: 202 });
  }

  return NextResponse.json({ ready: true, license: buildLicense(row) });
}
