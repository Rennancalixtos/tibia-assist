import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase";

function isAuthorized(request: Request): boolean {
  const token = request.headers.get("x-admin-token");
  return !!token && token === process.env.ADMIN_API_TOKEN;
}

export async function GET(request: Request) {
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: "Nao autorizado." }, { status: 401 });
  }

  const { data, error } = await supabaseAdmin
    .from("plans")
    .select("plan_id, days, price_cents, active, created_at, updated_at")
    .order("days", { ascending: true });

  if (error) {
    return NextResponse.json({ error: "Falha ao listar planos." }, { status: 500 });
  }

  return NextResponse.json({ plans: data });
}

/**
 * Upsert de plano (por plan_id) - usado tanto para criar um plano novo
 * quanto para editar preco/duracao/ativacao de um existente, sempre com o
 * mesmo verbo simples (sem painel admin, so este endpoint protegido por
 * x-admin-token).
 */
export async function POST(request: Request) {
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: "Nao autorizado." }, { status: 401 });
  }

  let body: { plan_id?: string; days?: number; price_cents?: number; active?: boolean };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Corpo da requisicao invalido." }, { status: 400 });
  }

  const { plan_id, days, price_cents, active } = body;

  if (!plan_id || typeof days !== "number" || typeof price_cents !== "number") {
    return NextResponse.json(
      { error: "Informe plan_id, days e price_cents validos." },
      { status: 400 }
    );
  }

  if (days <= 0 || price_cents <= 0) {
    return NextResponse.json(
      { error: "days e price_cents devem ser maiores que zero." },
      { status: 400 }
    );
  }

  const { error } = await supabaseAdmin.from("plans").upsert(
    {
      plan_id,
      days,
      price_cents,
      active: active ?? true,
    },
    { onConflict: "plan_id" }
  );

  if (error) {
    return NextResponse.json({ error: "Falha ao salvar plano." }, { status: 500 });
  }

  return NextResponse.json({ ok: true });
}
