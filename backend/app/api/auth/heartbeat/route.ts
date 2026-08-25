import { NextResponse } from "next/server";
import { supabaseAuth } from "@/lib/supabase";
import { touchSession } from "@/lib/license";

export async function POST(request: Request) {
  let body: { access_token?: string; session_token?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Corpo da requisicao invalido." }, { status: 400 });
  }

  const { access_token, session_token } = body;
  if (!access_token || !session_token) {
    return NextResponse.json({ error: "Informe access_token e session_token." }, { status: 400 });
  }

  const { data, error } = await supabaseAuth.auth.getUser(access_token);
  if (error || !data?.user) {
    return NextResponse.json({ error: "Sessao expirada. Faca login novamente." }, { status: 401 });
  }

  const result = await touchSession(data.user.id, session_token);
  if (result === "ok") {
    return NextResponse.json({ ok: true });
  }
  // "replaced" e "no_license" sao respostas normais (200), nao erros - o
  // cliente decide o que fazer com cada motivo.
  return NextResponse.json({ ok: false, reason: result });
}
