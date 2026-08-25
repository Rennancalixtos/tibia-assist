import { NextResponse } from "next/server";
import { fetchLatestExeRelease } from "@/lib/github";

// Sem cache: sempre reflete a release mais recente no momento do clique.
export const dynamic = "force-dynamic";

/**
 * Link estavel pra compartilhar (Discord, etc.) - sempre baixa a versao mais
 * recente publicada, sem precisar de login nem saber o asset_id de antemao.
 * So redireciona pra /api/update/download, que e quem de fato baixa o
 * binario do GitHub (repo privado) usando o token guardado no servidor.
 */
export async function GET(request: Request) {
  // preferInstaller: quem baixa por este link e sempre um usuario novo -
  // quer o instalador com atalho, nao o .exe portatil usado pelo auto-update.
  const release = await fetchLatestExeRelease(true);
  if (!release) {
    return NextResponse.json(
      { error: "Nenhuma versao publicada ainda. Tente novamente mais tarde." },
      { status: 404 }
    );
  }

  const origin = new URL(request.url).origin;
  const assetName = encodeURIComponent(release.assetName);
  return NextResponse.redirect(
    `${origin}/api/update/download?asset_id=${release.assetId}&asset_name=${assetName}`
  );
}
