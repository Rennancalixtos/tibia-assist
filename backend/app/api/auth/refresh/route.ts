import { NextResponse } from "next/server";
import { supabaseAuth } from "@/lib/supabase";
import { getLicenseForUser } from "@/lib/license";

function sessionExpiresAtIso(expiresAt: number | undefined, expiresIn: number | undefined): string {
  if (typeof expiresAt === "number") {
    return new Date(expiresAt * 1000).toISOString();
  }
  const seconds = typeof expiresIn === "number" ? expiresIn : 3600;
  return new Date(Date.now() + seconds * 1000).toISOString();
}

export async function POST(request: Request) {
  let body: { refresh_token?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Corpo da requisicao invalido." }, { status: 400 });
  }

  const { refresh_token } = body;

  if (!refresh_token) {
    return NextResponse.json(
      { error: "Informe o refresh_token." },
      { status: 400 }
    );
  }

  const { data, error } = await supabaseAuth.auth.refreshSession({ refresh_token });

  if (error || !data?.session) {
    return NextResponse.json(
      { error: "Sessao expirada. Faca login novamente." },
      { status: 401 }
    );
  }

  const { session } = data;
  const license = await getLicenseForUser(session.user.id);

  return NextResponse.json({
    access_token: session.access_token,
    refresh_token: session.refresh_token,
    expires_at: sessionExpiresAtIso(session.expires_at, session.expires_in),
    license,
  });
}
