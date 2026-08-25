import { supabaseAdmin } from "./supabase";

export type LicenseStatus =
  | "active"
  | "past_due"
  | "canceled"
  | "incomplete"
  | "not_found";

export type License = {
  valid: boolean;
  status: LicenseStatus;
  expires_at: string | null;
  reason?: string;
};

type LicenseRow = {
  status: string;
  current_period_end: string | null;
};

/**
 * Converte o status de assinatura do Stripe para o vocabulario aceito pela
 * tabela `licenses` / objeto `license` da API.
 * "active" | "past_due" | "canceled" | "incomplete" passam direto,
 * qualquer outro valor (trialing, unpaid, incomplete_expired, paused, ...)
 * cai em "incomplete".
 */
export function mapStripeStatus(stripeStatus: string): LicenseStatus {
  if (
    stripeStatus === "active" ||
    stripeStatus === "past_due" ||
    stripeStatus === "canceled" ||
    stripeStatus === "incomplete"
  ) {
    return stripeStatus;
  }
  return "incomplete";
}

/**
 * Monta o objeto `license` a partir de uma linha da tabela `licenses`
 * (ou `null` quando o usuario ainda nao tem nenhuma assinatura).
 * `valid` só é true quando status === "active" E expires_at está no futuro.
 */
export function buildLicense(row: LicenseRow | null): License {
  if (!row) {
    return {
      valid: false,
      status: "not_found",
      expires_at: null,
      reason: "Nenhuma assinatura encontrada para esta conta.",
    };
  }

  const status = row.status as LicenseStatus;
  const expiresAt = row.current_period_end;
  const isFuture = expiresAt ? new Date(expiresAt).getTime() > Date.now() : false;
  const valid = status === "active" && isFuture;

  const license: License = {
    valid,
    status,
    expires_at: expiresAt,
  };

  if (!valid) {
    license.reason =
      status !== "active"
        ? "Assinatura nao esta ativa."
        : "Assinatura expirada.";
  }

  return license;
}

/**
 * Busca a licenca do usuario no banco e devolve o objeto `license` pronto
 * para ser incluido na resposta da API.
 */
export async function getLicenseForUser(userId: string): Promise<License> {
  const { data, error } = await supabaseAdmin
    .from("licenses")
    .select("status, current_period_end")
    .eq("user_id", userId)
    .maybeSingle();

  if (error || !data) {
    return buildLicense(null);
  }

  return buildLicense(data as LicenseRow);
}

/**
 * Gera um novo token de sessao para `userId` e grava via UPDATE simples
 * (nunca upsert) - login/signup so chamam isto depois que a linha em
 * `licenses` ja existe, entao um UPDATE nunca insere uma linha parcial nem
 * toca nas colunas de assinatura (status/stripe_*) que nao estao no SET.
 * Se a linha ainda nao existir (conta sem nenhuma assinatura iniciada),
 * `count === 0` e o chamador simplesmente nao inclui session_token na
 * resposta - a conta segue sem fiscalizacao de sessao unica ate ter uma
 * linha (primeiro checkout).
 */
export async function issueSessionToken(userId: string): Promise<string | null> {
  const sessionToken = crypto.randomUUID();

  const { error, count } = await supabaseAdmin
    .from("licenses")
    .update({ session_token: sessionToken, session_heartbeat_at: new Date().toISOString() }, { count: "exact" })
    .eq("user_id", userId);

  if (error || !count) {
    return null;
  }
  return sessionToken;
}

export type HeartbeatResult = "ok" | "replaced" | "no_license";

/**
 * Atualiza `session_heartbeat_at` SOMENTE se `sessionToken` ainda for o
 * token vigente da conta - um unico UPDATE atomico (sem SELECT previo) para
 * nao ter uma janela de corrida entre checar e atualizar.
 */
export async function touchSession(userId: string, sessionToken: string): Promise<HeartbeatResult> {
  const { error, count } = await supabaseAdmin
    .from("licenses")
    .update({ session_heartbeat_at: new Date().toISOString() }, { count: "exact" })
    .eq("user_id", userId)
    .eq("session_token", sessionToken);

  if (error) {
    return "no_license";
  }
  if (count) {
    return "ok";
  }

  // 0 linhas afetadas: ou a conta nao tem licenca, ou o token nao bate mais
  // (outra sessao fez login depois). Distingue os dois pra nao rotular um
  // caso de "sem licenca" como "sessao substituida".
  const { data } = await supabaseAdmin
    .from("licenses")
    .select("user_id")
    .eq("user_id", userId)
    .maybeSingle();

  return data ? "replaced" : "no_license";
}

/**
 * Libera a conta imediatamente para login em outro lugar (chamado no logout
 * explicito, best-effort - falha aqui nao deve travar o logout do cliente).
 */
export async function clearSessionToken(userId: string): Promise<void> {
  await supabaseAdmin
    .from("licenses")
    .update({ session_token: null })
    .eq("user_id", userId);
}
