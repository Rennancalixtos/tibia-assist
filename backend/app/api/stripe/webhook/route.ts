import { NextResponse } from "next/server";
import type Stripe from "stripe";
import { stripe } from "@/lib/stripe";
import { supabaseAdmin } from "@/lib/supabase";
import { mapStripeStatus } from "@/lib/license";

// No App Router o `Request` nao é parseado automaticamente como JSON, entao
// basta ler `request.text()` para obter o corpo raw exigido pela verificacao
// de assinatura do Stripe. Forcamos rota dinamica para evitar qualquer cache.
export const dynamic = "force-dynamic";

function unixToIso(unixSeconds: number | null | undefined): string | null {
  if (!unixSeconds) return null;
  return new Date(unixSeconds * 1000).toISOString();
}

async function handleCheckoutCompleted(session: Stripe.Checkout.Session) {
  const subscriptionId =
    typeof session.subscription === "string" ? session.subscription : session.subscription?.id;

  if (!subscriptionId) {
    console.error("checkout.session.completed sem subscription id", session.id);
    return;
  }

  const subscription = await stripe.subscriptions.retrieve(subscriptionId);

  const userId =
    session.metadata?.user_id ?? (subscription.metadata?.user_id as string | undefined);

  if (!userId) {
    console.error("checkout.session.completed sem user_id nos metadados", session.id);
    return;
  }

  const customerId =
    typeof session.customer === "string" ? session.customer : session.customer?.id ?? null;

  const { error } = await supabaseAdmin.from("licenses").upsert(
    {
      user_id: userId,
      stripe_customer_id: customerId,
      stripe_subscription_id: subscription.id,
      status: mapStripeStatus(subscription.status),
      current_period_end: unixToIso(subscription.current_period_end),
    },
    { onConflict: "user_id" }
  );

  if (error) {
    console.error("Falha ao gravar licenca (checkout.session.completed)", error);
  }
}

async function handleSubscriptionUpdated(subscription: Stripe.Subscription) {
  const { error } = await supabaseAdmin
    .from("licenses")
    .update({
      status: mapStripeStatus(subscription.status),
      current_period_end: unixToIso(subscription.current_period_end),
    })
    .eq("stripe_subscription_id", subscription.id);

  if (error) {
    console.error("Falha ao atualizar licenca (customer.subscription.updated)", error);
  }
}

async function handleSubscriptionDeleted(subscription: Stripe.Subscription) {
  const { error } = await supabaseAdmin
    .from("licenses")
    .update({
      status: "canceled",
      current_period_end: unixToIso(subscription.current_period_end) ?? new Date().toISOString(),
    })
    .eq("stripe_subscription_id", subscription.id);

  if (error) {
    console.error("Falha ao atualizar licenca (customer.subscription.deleted)", error);
  }
}

export async function POST(request: Request) {
  const signature = request.headers.get("stripe-signature");
  const rawBody = await request.text();

  if (!signature) {
    return NextResponse.json({ error: "Assinatura ausente." }, { status: 400 });
  }

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(
      rawBody,
      signature,
      process.env.STRIPE_WEBHOOK_SECRET as string
    );
  } catch (err) {
    console.error("Falha na verificacao da assinatura do webhook", err);
    return NextResponse.json({ error: "Assinatura invalida." }, { status: 400 });
  }

  switch (event.type) {
    case "checkout.session.completed":
      await handleCheckoutCompleted(event.data.object as Stripe.Checkout.Session);
      break;
    case "customer.subscription.updated":
      await handleSubscriptionUpdated(event.data.object as Stripe.Subscription);
      break;
    case "customer.subscription.deleted":
      await handleSubscriptionDeleted(event.data.object as Stripe.Subscription);
      break;
    default:
      // Outros eventos sao ignorados de proposito.
      break;
  }

  return NextResponse.json({ received: true });
}
