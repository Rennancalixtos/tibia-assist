import { NextResponse } from "next/server";

// Sem cache: cada checagem do app desktop deve ver o release mais recente.
export const dynamic = "force-dynamic";

/**
 * Consulta o release mais recente do repositorio (privado) no GitHub usando
 * um token guardado so no servidor - o app desktop nunca fala com o GitHub
 * diretamente (nao ha como embutir um token no binario com seguranca).
 *
 * Devolve {version, notes, asset_id, asset_name, size}. `asset_id` e usado
 * depois por /api/update/download para buscar o binario.
 */
export async function GET() {
  const token = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO; // formato "owner/repo"

  if (!token || !repo) {
    return NextResponse.json(
      { error: "Checagem de atualizacao nao configurada no servidor." },
      { status: 500 }
    );
  }

  let res: Response;
  try {
    res = await fetch(`https://api.github.com/repos/${repo}/releases/latest`, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: "Falha ao consultar o GitHub." }, { status: 502 });
  }

  if (!res.ok) {
    return NextResponse.json(
      { error: `GitHub respondeu ${res.status} ao buscar o release.` },
      { status: 502 }
    );
  }

  const release = await res.json();
  const assets: Array<{ id: number; name: string; size: number }> = release.assets || [];
  // O auto-update silencioso precisa do build PORTATIL (troca em runtime,
  // sem wizard) - nunca do instalador NSIS (*-Setup.exe), que abre uma
  // janela e pede clique. Desde a migracao pra --onedir o portatil e um
  // .zip (pasta inteira do app); mantemos o fallback pro .exe solto por
  // causa de releases antigas (onefile) que ainda podem ficar "latest".
  const zipAsset = assets.find((a) => a.name?.toLowerCase().endsWith(".zip"));
  const exeAsset = assets.find((a) => {
    const name = a.name?.toLowerCase() || "";
    return name.endsWith(".exe") && !name.includes("setup") && !name.includes("install");
  });
  const portableAsset = zipAsset ?? exeAsset;

  return NextResponse.json({
    version: release.tag_name || null,
    notes: release.body || "",
    asset_id: portableAsset?.id ?? null,
    asset_name: portableAsset?.name ?? null,
    size: portableAsset?.size ?? null,
  });
}
