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
