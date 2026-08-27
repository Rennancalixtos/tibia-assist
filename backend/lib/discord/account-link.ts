import { supabaseAdmin } from "@/lib/supabase";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_LIST_PAGES = 20;
const PAGE_SIZE = 1000;

export function isValidEmailFormat(email: string): boolean {
  return EMAIL_RE.test(email.trim());
}

export type LinkedAccount = {
  userId: string;
  email: string;
};

/**
 * Resolve o user_id do Supabase a partir do e-mail digitado no modal do
 * Discord. Nao ha OAuth do Discord nem coluna de e-mail replicada fora do
 * auth.users, entao a unica forma de achar a conta e paginar a Admin API
 * (nao ha filtro nativo por e-mail nesta versao do supabase-js). Cortado em
 * MAX_LIST_PAGES paginas pra nunca rodar sem fim numa base grande demais.
 */
export async function resolveAccountByEmail(email: string): Promise<LinkedAccount | null> {
  const normalized = email.trim().toLowerCase();
  if (!isValidEmailFormat(normalized)) {
    return null;
  }

  for (let page = 1; page <= MAX_LIST_PAGES; page++) {
    const { data, error } = await supabaseAdmin.auth.admin.listUsers({ page, perPage: PAGE_SIZE });
    if (error || !data?.users?.length) {
      return null;
    }
    const match = data.users.find((u) => (u.email ?? "").toLowerCase() === normalized);
    if (match) {
      return { userId: match.id, email: match.email ?? normalized };
    }
    if (data.users.length < PAGE_SIZE) {
      return null;
    }
  }
  return null;
}
