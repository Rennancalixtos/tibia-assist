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
  const release = await fetchLatestExeRelease();
  if (!release) {
    return NextResponse.json(
      { error: "Nenhuma versao publicada ainda. Tente novamente mais tarde." },
      { status: 404 }
    );
  }

  const origin = new URL(request.url).origin;
  return NextResponse.redirect(`${origin}/api/update/download?asset_id=${release.assetId}`);
}
