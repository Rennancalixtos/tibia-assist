import { NextResponse } from "next/server";

// Sem cache/buffer - o arquivo e transmitido direto do GitHub pro cliente.
export const dynamic = "force-dynamic";

/**
 * Repassa (proxy) o binario de um asset de release do GitHub (repo privado)
 * para o app desktop, sem nunca expor o token do GitHub a ele.
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const assetId = url.searchParams.get("asset_id");
  if (!assetId) {
    return NextResponse.json({ error: "Informe asset_id." }, { status: 400 });
  }

  // Nome pra salvar o arquivo (opcional - quem redireciona pra aqui, como
  // /download, ja sabe o nome real do asset escolhido). Sanitizado porque
  // vai direto pro header; sem isso (ex: chamada direta do updater), cai
  // num nome generico - o Content-Disposition so importa pra quem baixa
  // pelo navegador, o updater do app desktop ja nomeia o arquivo sozinho.
  const requestedName = (url.searchParams.get("asset_name") || "").replace(/[^\w.\-]/g, "");
  const fileName = requestedName || "EasyF.exe";

  const token = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO;
  if (!token || !repo) {
    return NextResponse.json(
      { error: "Checagem de atualizacao nao configurada no servidor." },
      { status: 500 }
    );
  }

  let res: Response;
  try {
    res = await fetch(`https://api.github.com/repos/${repo}/releases/assets/${assetId}`, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/octet-stream",
      },
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: "Falha ao buscar o arquivo no GitHub." }, { status: 502 });
  }

  if (!res.ok || !res.body) {
    return NextResponse.json(
      { error: `GitHub respondeu ${res.status} ao buscar o asset.` },
      { status: 502 }
    );
  }

  return new NextResponse(res.body, {
    headers: {
      "Content-Type": "application/octet-stream",
      "Content-Disposition": `attachment; filename="${fileName}"`,
    },
  });
}
