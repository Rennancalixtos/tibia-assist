import Stripe from "stripe";

/**
 * Cliente Stripe configurado com a chave secreta do servidor.
 */
export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY as string, {
  apiVersion: "2024-06-20",
});
