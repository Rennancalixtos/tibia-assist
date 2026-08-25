import { NextResponse } from "next/server";
import { supabaseAdmin, supabaseAuth } from "@/lib/supabase";
import { buildLicense } from "@/lib/license";

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

  const { data: createdUser, error: createError } = await supabaseAdmin.auth.admin.createUser({
    email,
    password,
    email_confirm: true,
  });

  if (createError || !createdUser?.user) {
    const message = createError?.message ?? "";
    let errorMessage = "Nao foi possivel criar a conta.";

    if (message.toLowerCase().includes("already") || message.toLowerCase().includes("registered")) {
      errorMessage = "Este email ja esta cadastrado.";
    } else if (message.toLowerCase().includes("password")) {
      errorMessage = "A senha e muito fraca. Use pelo menos 6 caracteres.";
    } else if (message.toLowerCase().includes("email")) {
      errorMessage = "Email invalido.";
    }

    return NextResponse.json({ error: errorMessage }, { status: 400 });
  }

  const { data: signInData, error: signInError } = await supabaseAuth.auth.signInWithPassword({
    email,
    password,
  });

  if (signInError || !signInData?.session) {
    return NextResponse.json(
      { error: "Conta criada, mas falhou ao iniciar sessao. Tente fazer login." },
      { status: 400 }
    );
  }

  const { session } = signInData;

  return NextResponse.json({
    access_token: session.access_token,
    refresh_token: session.refresh_token,
    expires_at: sessionExpiresAtIso(session.expires_at, session.expires_in),
    license: buildLicense(null),
  });
}
