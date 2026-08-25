import { NextResponse } from "next/server";
import { supabaseAuth } from "@/lib/supabase";
import { clearSessionToken } from "@/lib/license";

/**
 * Logout explicito: libera a conta pra login em outro lugar imediatamente,
 * sem esperar o token antigo sobreviver ate o proximo heartbeat de quem
 * eventualmente tentar logar de novo. Best-effort - o cliente ja limpa o
 * estado local independente do resultado disto.
 */
export async function POST(request: Request) {
  let body: { access_token?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Corpo da requisicao invalido." }, { status: 400 });
  }

  const { access_token } = body;
  if (!access_token) {
    return NextResponse.json({ error: "Informe access_token." }, { status: 400 });
  }

  const { data, error } = await supabaseAuth.auth.getUser(access_token);
  if (error || !data?.user) {
    return NextResponse.json({ ok: true });
  }

  await clearSessionToken(data.user.id);
  return NextResponse.json({ ok: true });
}
