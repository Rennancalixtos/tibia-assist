import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.SUPABASE_URL as string;
const supabaseAnonKey = process.env.SUPABASE_ANON_KEY as string;
const supabaseServiceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY as string;

/**
 * Cliente administrativo do Supabase (service role key).
 * Usado no servidor para criar/consultar usuarios via Admin API e para
 * ler/escrever na tabela `licenses`. Nunca deve ser exposto ao cliente.
 */
export const supabaseAdmin = createClient(supabaseUrl, supabaseServiceRoleKey, {
  auth: {
    autoRefreshToken: false,
    persistSession: false,
  },
});

/**
 * Cliente de autenticacao do Supabase (anon key).
 * Usado para operacoes feitas em nome do usuario final: login por senha,
 * renovacao de sessao (refresh token) e validacao de access token (getUser).
 */
export const supabaseAuth = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    autoRefreshToken: false,
    persistSession: false,
  },
});
