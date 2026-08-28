from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_API_BASE_URL = "https://tibia-assist.vercel.app"


def load_admin_token() -> str:
    token = os.environ.get("ADMIN_API_TOKEN")
    if token:
        return token

    env_path = os.path.join(os.path.dirname(__file__), "backend", ".env")
    if os.path.isfile(env_path):
        with open(env_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith("ADMIN_API_TOKEN="):
                    return line.split("=", 1)[1].strip()

    print("ADMIN_API_TOKEN não encontrado (defina a variável de ambiente ou backend/.env).", file=sys.stderr)
    sys.exit(1)


def request(method: str, path: str, api_base_url: str, token: str, payload: dict | None = None) -> dict:
    url = f"{api_base_url.rstrip('/')}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"x-admin-token": token, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        print(f"Erro HTTP {exc.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Falha ao conectar com {url}: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_list(args: argparse.Namespace) -> None:
    result = request("GET", "/api/admin/plans", args.api_base_url, args.token)
    for plan in result.get("plans", []):
        reais = plan["price_cents"] / 100
        status = "ativo" if plan["active"] else "inativo"
        print(f"{plan['plan_id']:>4}  {plan['days']:>3} dias  R$ {reais:,.2f}  [{status}]")


def cmd_set_price(args: argparse.Namespace) -> None:
    price_cents = round(args.reais * 100)
    payload = {
        "plan_id": args.plan_id,
        "days": args.days,
        "price_cents": price_cents,
        "active": not args.inactive,
    }
    request("POST", "/api/admin/plans", args.api_base_url, args.token, payload)
    print(f"Plano {args.plan_id} atualizado: {args.days} dias por R$ {args.reais:,.2f}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gerencia os planos de licença (dias/preço) do backend EasyF.")
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="Lista os planos e preços atuais.")
    list_parser.set_defaults(func=cmd_list)

    set_parser = subparsers.add_parser("set-price", help="Cria ou atualiza um plano (dias/preço).")
    set_parser.add_argument("plan_id", help="Identificador do plano, ex: 7d, 15d, 30d.")
    set_parser.add_argument("days", type=int, help="Duração do plano em dias.")
    set_parser.add_argument("reais", type=float, help="Preço em reais, ex: 5 ou 19.90.")
    set_parser.add_argument("--inactive", action="store_true", help="Marca o plano como inativo (indisponível para compra).")
    set_parser.set_defaults(func=cmd_set_price)

    args = parser.parse_args()
    args.token = load_admin_token()
    args.func(args)


if __name__ == "__main__":
    main()
