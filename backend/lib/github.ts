const GITHUB_API = "https://api.github.com";

export type LatestExeRelease = {
  version: string;
  notes: string;
  assetId: number;
  assetName: string;
  size: number;
};

/**
 * Busca o release mais recente do repo (privado) no GitHub e acha o asset
 * ".exe" anexado, usando o token guardado so no servidor. Devolve null se
 * nao houver release, nao houver asset .exe, ou as env vars nao estiverem
 * configuradas - nunca lanca, quem chamar decide como reportar isso.
 */
export async function fetchLatestExeRelease(): Promise<LatestExeRelease | null> {
  const token = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO;
  if (!token || !repo) return null;

  let res: Response;
  try {
    res = await fetch(`${GITHUB_API}/repos/${repo}/releases/latest`, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      cache: "no-store",
    });
  } catch {
    return null;
  }
  if (!res.ok) return null;

  const release = await res.json();
  const assets: Array<{ id: number; name: string; size: number }> = release.assets || [];
  const exeAsset = assets.find((a) => a.name?.toLowerCase().endsWith(".exe"));
  if (!exeAsset) return null;

  return {
    version: release.tag_name || "",
    notes: release.body || "",
    assetId: exeAsset.id,
    assetName: exeAsset.name,
    size: exeAsset.size,
  };
}
