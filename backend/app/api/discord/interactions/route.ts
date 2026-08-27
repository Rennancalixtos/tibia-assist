import { NextResponse } from "next/server";
import { verifyDiscordRequest, InteractionType, InteractionResponseType, ephemeralReply } from "@/lib/discord/core";
import {
  TRIAL_COMMAND_NAME,
  handleTrialCommand,
  handleTrialModalSubmit,
  handleTrialComponent,
} from "@/lib/discord/commands/trial";
import {
  PURCHASE_COMMAND_NAME,
  handlePurchaseCommand,
  handlePurchaseModalSubmit,
  handlePurchaseComponent,
} from "@/lib/discord/commands/purchase";

// O Discord exige resposta em ate 3s e reenvia a interacao (com um novo ID)
// se nao receber - por isso a rota so faz trabalho sincrono rapido, sem
// tocar em Stripe/Mercado Pago/Supabase de forma lenta demais. Assinatura
// verificada via Ed25519 (x-signature-ed25519/x-signature-timestamp), exigida
// pelo Discord pra qualquer endpoint de Interactions.
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const rawBody = await request.text();
  const signature = request.headers.get("x-signature-ed25519");
  const timestamp = request.headers.get("x-signature-timestamp");

  if (!verifyDiscordRequest(rawBody, signature, timestamp)) {
    return NextResponse.json({ error: "Assinatura invalida." }, { status: 401 });
  }

  const interaction = JSON.parse(rawBody);

  if (interaction.type === InteractionType.PING) {
    return NextResponse.json({ type: InteractionResponseType.PONG });
  }

  if (interaction.type === InteractionType.APPLICATION_COMMAND) {
    const name = interaction.data?.name;
    if (name === TRIAL_COMMAND_NAME) {
      return NextResponse.json(await handleTrialCommand(interaction));
    }
    if (name === PURCHASE_COMMAND_NAME) {
      return NextResponse.json(await handlePurchaseCommand(interaction));
    }
    return NextResponse.json(ephemeralReply("Comando desconhecido."));
  }

  if (interaction.type === InteractionType.MODAL_SUBMIT) {
    const customId: string = interaction.data?.custom_id ?? "";
    if (customId.startsWith("trial:")) {
      return NextResponse.json(await handleTrialModalSubmit(interaction));
    }
    if (customId.startsWith("purchase:")) {
      return NextResponse.json(await handlePurchaseModalSubmit(interaction));
    }
  }

  if (interaction.type === InteractionType.MESSAGE_COMPONENT) {
    const customId: string = interaction.data?.custom_id ?? "";
    if (customId.startsWith("trial:")) {
      return NextResponse.json(await handleTrialComponent(interaction, customId));
    }
    if (customId.startsWith("purchase:")) {
      return NextResponse.json(await handlePurchaseComponent(interaction, customId));
    }
  }

  return NextResponse.json(ephemeralReply("Interacao nao suportada."));
}
