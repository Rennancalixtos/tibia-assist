import { NextResponse } from "next/server";
import { supabaseAdmin, supabaseAuth } from "@/lib/supabase";
import { stripe } from "@/lib/stripe";

export async function POST(request: Request) {
  let body: { access_token?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Corpo da requisicao invalido." }, { status: 400 });
  }

  const { access_token } = body;

  if (!access_token) {
    return NextResponse.json({ error: "Informe o access_token." }, { status: 400 });
  }

  const { data: userData, error: userError } = await supabaseAuth.auth.getUser(access_token);

  if (userError || !userData?.user) {
    return NextResponse.json({ error: "Sessao invalida." }, { status: 401 });
  }

  const { id: userId, email } = userData.user;

  // Busca uma linha de licenca existente para reaproveitar o customer do Stripe, se houver.
  const { data: existingLicense } = await supabaseAdmin
    .from("licenses")
    .select("stripe_customer_id")
    .eq("user_id", userId)
    .maybeSingle();

  let customerId = existingLicense?.stripe_customer_id as string | undefined;

  if (!customerId) {
    const customer = await stripe.customers.create({
      email: email ?? undefined,
      metadata: { user_id: userId },
    });
    customerId = customer.id;

    // Garante que exista uma linha de licenca associada ao customer criado,
    // sem sobrescrever status/periodo caso ja exista uma linha (upsert por user_id).
    await supabaseAdmin
      .from("licenses")
      .upsert(
        { user_id: userId, stripe_customer_id: customerId },
        { onConflict: "user_id" }
      );
  }

  const origin = request.headers.get("origin") ?? new URL(request.url).origin;

  const checkoutSession = await stripe.checkout.sessions.create({
    mode: "subscription",
    customer: customerId,
    line_items: [{ price: process.env.STRIPE_PRICE_ID as string, quantity: 1 }],
    success_url: `${origin}/success?session_id={CHECKOUT_SESSION_ID}`,
    cancel_url: `${origin}/`,
    metadata: { user_id: userId },
    subscription_data: {
      metadata: { user_id: userId },
    },
  });

  return NextResponse.json({ url: checkoutSession.url });
}
