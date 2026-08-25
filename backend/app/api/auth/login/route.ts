import { NextResponse } from "next/server";
import { supabaseAuth } from "@/lib/supabase";
import { getLicenseForUser, issueSessionToken } from "@/lib/license";

function sessionExpiresAtIso(expiresAt: number | undefined, expiresIn: number | undefined): string {
  if (typeof expiresAt === "number") {
    return new Date(expiresAt * 1000).toISOString();
  }
  const seconds = typeof expiresIn === "number" ? expiresIn : 3600;
  return new Date(Date.now() + seconds * 1000).toISOString();
}

export async function POST(request: Request) {
  let body: { email?: string; password?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Corpo da requisicao invalido." }, { status: 400 });
  }

  const { email, password } = body;

  if (!email || !password) {
    return NextResponse.json(
      { error: "Informe email e senha." },
      { status: 400 }
    );
  }

  const { data, error } = await supabaseAuth.auth.signInWithPassword({ email, password });

  if (error || !data?.session) {
    return NextResponse.json({ error: "Credenciais invalidas." }, { status: 401 });
  }

  const { session } = data;
  const license = await getLicenseForUser(session.user.id);
  // null quando a conta ainda nao tem nenhuma linha em `licenses` (nunca
  // fez checkout) - a conta so passa a ter sessao unica fiscalizada depois
  // do primeiro checkout/ativacao.
  const sessionToken = await issueSessionToken(session.user.id);

  return NextResponse.json({
    access_token: session.access_token,
    refresh_token: session.refresh_token,
    expires_at: sessionExpiresAtIso(session.expires_at, session.expires_in),
    license,
    ...(sessionToken ? { session_token: sessionToken } : {}),
  });
}
