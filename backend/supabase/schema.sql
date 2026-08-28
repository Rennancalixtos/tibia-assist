-- Tabela de licencas/assinaturas do EasyF.
-- Cada usuario de auth.users tem no maximo uma linha aqui.
create table if not exists public.licenses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  stripe_customer_id text,
  stripe_subscription_id text,
  status text not null default 'incomplete',
  current_period_end timestamptz,
  -- Sessao unica por conta: token opaco gerado a cada login, comparado pelo
  -- heartbeat periodico do cliente. NULL = nenhuma sessao ativa fiscalizada
  -- ainda (conta nunca logou depois desta feature existir).
  session_token text,
  session_heartbeat_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Para quem ja tinha a tabela criada antes desta feature existir:
--   alter table public.licenses add column if not exists session_token text;
--   alter table public.licenses add column if not exists session_heartbeat_at timestamptz;

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

-- RLS bloqueia por LINHA, mas o Postgres ainda exige GRANT pra role poder
-- acessar a tabela. Com "Automatically expose new tables" desabilitado, o
-- Supabase nao concede esses grants automaticamente - sem isso o service_role
-- (usado pelo backend) recebe "permission denied for table licenses" mesmo
-- ignorando RLS. So o service_role recebe privilegio aqui; anon/authenticated
-- continuam sem nenhum acesso.
grant usage on schema public to service_role;
grant select, insert, update, delete on public.licenses to service_role;

-- Trial gratis (Discord) e Mercado Pago: 'licenses' ganha 'plan_type' (para
-- diferenciar assinatura paga de teste gratis concedido manualmente) e
-- 'payment_provider' (para saber se a ultima cobranca veio do Stripe ou do
-- Mercado Pago - os dois coexistem, o campo so registra a origem).
alter table public.licenses add column if not exists plan_type text not null default 'paid';
alter table public.licenses add column if not exists payment_provider text;

-- Planos fixos vendidos via Mercado Pago (7/15/30 dias). Preco e duracao
-- ficam so aqui - o endpoint de checkout do Mercado Pago recebe apenas o
-- plan_id do cliente/bot do Discord e resolve tudo a partir desta tabela,
-- nunca confia em dias/preco vindos do client.
create table if not exists public.plans (
  plan_id text primary key,
  days integer not null check (days > 0),
  price_cents integer not null check (price_cents > 0),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists plans_set_updated_at on public.plans;

create trigger plans_set_updated_at
  before update on public.plans
  for each row
  execute function public.set_licenses_updated_at();

insert into public.plans (plan_id, days, price_cents, active) values
  ('7d', 7, 1990, true),
  ('15d', 15, 3490, true),
  ('30d', 30, 5990, true)
on conflict (plan_id) do nothing;

-- Mesmo padrao de 'licenses': RLS ligada e sem nenhuma policy bloqueia
-- anon/authenticated por completo; so o service_role (que ignora RLS) acessa.
alter table public.plans enable row level security;

grant select, insert, update, delete on public.plans to service_role;

-- Solicitacoes de teste gratis abertas via comando do Discord. Quantidade de
-- horas concedida e sempre a config global do backend (nunca decidida pelo
-- bot/cliente); 'status' comeca 'pending' e vira 'approved'/'rejected' quando
-- um admin decide via botao no Discord. Um usuario so pode ter uma
-- solicitacao (de qualquer status) por conta, pra nao dar pra pedir de novo.
create table if not exists public.trial_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  discord_user_id text not null,
  status text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  hours_granted integer,
  reason text,
  decided_by_discord_id text,
  requested_at timestamptz not null default now(),
  decided_at timestamptz
);

create index if not exists trial_requests_status_idx on public.trial_requests (status);

alter table public.trial_requests enable row level security;

grant select, insert, update, delete on public.trial_requests to service_role;

-- Idempotencia do webhook do Mercado Pago: cada payment_id so pode ser
-- processado uma vez (webhooks do MP podem reenviar a mesma notificacao).
-- O webhook insere aqui ANTES de aplicar o upsert em licenses; um
-- payment_id repetido bate na PK e a notificacao e respondida 200 sem
-- reprocessar.
create table if not exists public.mercadopago_payments (
  payment_id text primary key,
  user_id uuid not null,
  plan_id text not null,
  processed_at timestamptz not null default now()
);

-- Guarda o token da interacao do Discord (valido por so 15 minutos) e um
-- status proprio - permite ao webhook EDITAR a mensagem original do QR code
-- (em vez de so mandar DM) quando o pagamento e aprovado dentro dessa janela.
-- A linha e inserida no momento da criacao do PIX (status 'pending'), e o
-- webhook faz UPDATE pra 'processed' em vez de INSERT, pra nao colidir com a
-- PK e ainda permitir recuperar o interaction_token guardado.
alter table public.mercadopago_payments add column if not exists interaction_token text;
alter table public.mercadopago_payments add column if not exists status text not null default 'processed' check (status in ('pending', 'processed'));

alter table public.mercadopago_payments enable row level security;

grant select, insert, update, delete on public.mercadopago_payments to service_role;

-- Tickets de suporte abertos via botao no Discord (canal privado criado por
-- ticket, com o bot). Nao exige conta no EasyF - identidade e so o
-- discord_user_id. O indice parcial garante consulta rapida por "ja tem
-- ticket aberto" sem precisar checar todo o historico.
create table if not exists public.support_tickets (
  id uuid primary key default gen_random_uuid(),
  channel_id text not null unique,
  discord_user_id text not null,
  status text not null default 'open' check (status in ('open', 'closed')),
  opened_at timestamptz not null default now(),
  closed_at timestamptz
);

create index if not exists support_tickets_open_by_user_idx
  on public.support_tickets (discord_user_id)
  where status = 'open';

alter table public.support_tickets enable row level security;

grant select, insert, update, delete on public.support_tickets to service_role;
