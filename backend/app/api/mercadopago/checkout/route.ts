import { NextResponse } from "next/server";
import { supabaseAuth } from "@/lib/supabase";
import { createCheckoutForUser } from "@/lib/mercadopago";

export async function POST(request: Request) {
  let body: { access_token?: string; plan_id?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Corpo da requisicao invalido." }, { status: 400 });
  }

  const { access_token, plan_id } = body;

  if (!access_token || !plan_id) {
    return NextResponse.json({ error: "Informe access_token e plan_id." }, { status: 400 });
  }

  const { data: userData, error: userError } = await supabaseAuth.auth.getUser(access_token);

  if (userError || !userData?.user) {
    return NextResponse.json({ error: "Sessao invalida." }, { status: 401 });
  }

  const result = await createCheckoutForUser(userData.user.id, plan_id);

  if ("error" in result) {
    return NextResponse.json({ error: result.error }, { status: 400 });
  }

  return NextResponse.json({ url: result.url });
}
