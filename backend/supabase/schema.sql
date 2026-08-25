-- Tabela de licencas/assinaturas do TibiaAssist.
-- Cada usuario de auth.users tem no maximo uma linha aqui.
create table if not exists public.licenses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  stripe_customer_id text,
  stripe_subscription_id text,
  status text not null default 'incomplete',
  current_period_end timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists licenses_stripe_subscription_id_idx
  on public.licenses (stripe_subscription_id);

create index if not exists licenses_stripe_customer_id_idx
  on public.licenses (stripe_customer_id);

-- Mantem updated_at sempre atualizado a cada UPDATE na linha.
create or replace function public.set_licenses_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists licenses_set_updated_at on public.licenses;

create trigger licenses_set_updated_at
  before update on public.licenses
  for each row
  execute function public.set_licenses_updated_at();

-- So o backend (service_role, que ignora RLS) le/escreve nesta tabela.
-- RLS habilitada e sem nenhuma policy = acesso publico (anon/authenticated)
-- totalmente bloqueado, mesmo que a tabela seja exposta na Data API.
alter table public.licenses enable row level security;
