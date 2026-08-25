# Backend TibiaAssist (licenca via Supabase Auth + Stripe)

Backend em Next.js 14 (App Router) responsavel por:

- Cadastro e login por email/senha (Supabase Auth).
- Cobranca recorrente da assinatura (Stripe Checkout + Webhook).
- Consulta do status da licenca (embutida nas respostas de login/refresh).

O app desktop TibiaAssist chama este backend diretamente por HTTP (nao usa
esta pagina web para login, apenas para cadastro + inicio do pagamento).

## 1. Criar o projeto no Supabase

1. Crie um projeto em https://supabase.com/dashboard.
2. Em **Authentication > Providers**, confirme que o provider **Email** esta
   habilitado com login por senha (é o padrao). Nao é necessario configurar
   templates de confirmacao de email: o backend cria usuarios com
   `email_confirm: true`, ou seja, sem etapa de confirmacao por email.
3. Em **Project Settings > API**, anote:
   - `Project URL` -> variavel `SUPABASE_URL`
   - `anon public` key -> variavel `SUPABASE_ANON_KEY`
   - `service_role` key -> variavel `SUPABASE_SERVICE_ROLE_KEY` (mantenha em
     segredo, nunca exponha no frontend)
4. Abra o **SQL Editor** do Supabase e execute o conteudo de
   `backend/supabase/schema.sql` para criar a tabela `licenses`, os indices,
   o trigger de `updated_at` e habilitar Row Level Security (sem nenhuma
   policy, ou seja, acesso publico bloqueado por completo).
5. Se aparecer a opcao **"Automatically expose new tables"** durante a
   criacao do projeto/tabela, **desabilite**. So o backend acessa `licenses`,
   sempre com a `service_role` key (que ignora RLS) - nunca pela Data API
   publica (PostgREST), entao nao ha motivo pra expor a tabela ali.

## 2. Criar o produto e o preco no Stripe

1. Crie uma conta/projeto em https://dashboard.stripe.com.
2. Em **Product catalog**, crie um produto (ex: "TibiaAssist - Assinatura
   mensal") com um preco **recorrente** (recurring). Copie o `price id`
   (comeca com `price_...`) -> variavel `STRIPE_PRICE_ID`.
3. Em **Developers > API keys**, copie a **Secret key** -> variavel
   `STRIPE_SECRET_KEY`.

## 3. Configurar o Webhook do Stripe

1. Em **Developers > Webhooks**, clique em **Add endpoint**.
2. URL do endpoint: `https://<seu-dominio>/api/stripe/webhook`.
3. Selecione os eventos:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
4. Depois de criar, copie o **Signing secret** (comeca com `whsec_...`) ->
   variavel `STRIPE_WEBHOOK_SECRET`.

> Durante o desenvolvimento local, use `stripe listen --forward-to
> localhost:3000/api/stripe/webhook` (Stripe CLI) para receber eventos e
> obter um signing secret temporario.

## 4. Variaveis de ambiente

Copie `.env.example` para `.env.local` e preencha:

```
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_ID=
```

## 5. Rodando localmente

```
npm install
npm run dev
```

A pagina inicial (`/`) fica disponivel em `http://localhost:3000`.

## 6. Deploy na Vercel

1. Importe o repositorio na Vercel, apontando o **Root Directory** para
   `backend/`.
2. Em **Settings > Environment Variables**, adicione as mesmas variaveis do
   passo 4 (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
   `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID`).
3. Faca o deploy. Depois de publicado, atualize a URL do endpoint de webhook
   no Stripe (passo 3) para a URL final da Vercel, se ainda nao tiver feito.

## 7. Endpoints da API

Todas as respostas sao JSON. Erros de entrada invalida ou autenticacao
retornam `{"error": "<mensagem>"}` com status 400 (entrada invalida) ou 401
(credenciais/sessao invalida). O restante retorna 200.

- `POST /api/auth/signup` - `{email, password}` -> cria o usuario no
  Supabase Auth (ja confirmado) e devolve
  `{access_token, refresh_token, expires_at, license}` (licenca ainda nao
  paga: `status: "not_found"`, `valid: false`).
- `POST /api/auth/login` - `{email, password}` -> mesma resposta do signup,
  com a licenca real do usuario. 401 se as credenciais forem invalidas.
- `POST /api/auth/refresh` - `{refresh_token}` -> renova a sessao (o
  Supabase rotaciona o refresh token) e devolve a licenca atualizada na
  mesma chamada. O app desktop chama este endpoint na inicializacao e
  periodicamente (ex: a cada 30 min).
- `POST /api/stripe/checkout` - `{access_token}` -> valida o token no
  Supabase, cria/reaproveita o Customer no Stripe e devolve
  `{url}` da Stripe Checkout Session (modo assinatura).
- `POST /api/stripe/webhook` - recebido pelo Stripe, atualiza a tabela
  `licenses` conforme o evento.
- `GET /api/license/by-session?session_id=...` - usado pela pagina de
  sucesso enquanto o webhook ainda nao processou: `{ready: false}` (202)
  ou `{ready: true, license}` (200).

## 8. Configurando o app desktop

No `config.json` do TibiaAssist (raiz do repositorio, fora de `backend/`),
defina a URL publicada deste backend em `license.api_base_url`, por exemplo:

```json
{
  "license": {
    "api_base_url": "https://seu-backend.vercel.app"
  }
}
```

O app desktop tem sua propria tela de login (email/senha) que chama
`/api/auth/login` e `/api/auth/refresh` diretamente nesse endereco.
