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
 *
 * Uma release pode ter DOIS .exe: o portatil (usado pelo auto-update
 * silencioso) e o instalador NSIS ("*-Setup.exe" ou "*-Install*.exe", com
 * wizard/atalho). `preferInstaller` escolhe qual dos dois pegar quando os
 * dois existem - com fallback pro outro se so um foi publicado (ex: a
 * primeira release, antes do instalador existir).
 */
export async function fetchLatestExeRelease(preferInstaller = false): Promise<LatestExeRelease | null> {
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
  const exeAssets = assets.filter((a) => a.name?.toLowerCase().endsWith(".exe"));
  if (!exeAssets.length) return null;

  const isInstaller = (name: string) => /setup|install/i.test(name);
  const exeAsset = preferInstaller
    ? exeAssets.find((a) => isInstaller(a.name)) ?? exeAssets.find((a) => !isInstaller(a.name))
    : exeAssets.find((a) => !isInstaller(a.name)) ?? exeAssets[0];
  if (!exeAsset) return null;

  return {
    version: release.tag_name || "",
    notes: release.body || "",
    assetId: exeAsset.id,
    assetName: exeAsset.name,
    size: exeAsset.size,
  };
}
