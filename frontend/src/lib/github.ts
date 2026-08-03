/* Turns the indexed repository URL into links back to GitHub.
 *
 * The API already returns citations as `path/file.py:12-30` and short commit
 * hashes; knowing the repo is all that is needed to make those clickable, so
 * this is entirely a frontend concern and the backend is untouched.
 */

export interface GitHubRepo {
  owner: string;
  name: string;
  /** Canonical https URL, with any `.git` suffix removed. */
  url: string;
}

export function parseGitHubRepo(repoUrl: string): GitHubRepo | null {
  let url: URL;
  try {
    url = new URL(repoUrl);
  } catch {
    return null;
  }

  // Only GitHub gets deep links. A GitLab or self-hosted repo still indexes
  // fine, its citations just stay plain text.
  if (url.hostname !== "github.com" && url.hostname !== "www.github.com") {
    return null;
  }

  const [owner, rawName] = url.pathname.replace(/^\/+/, "").split("/");
  if (!owner || !rawName) return null;

  const name = rawName.replace(/\.git$/, "");
  return { owner, name, url: `https://github.com/${owner}/${name}` };
}

/** Deep link to a line range.
 *
 * `HEAD` rather than a branch name: the indexer clones the default branch, and
 * HEAD resolves to it whether the repo calls it main, master, or anything else.
 */
export function blobUrl(
  repo: GitHubRepo,
  path: string,
  startLine: number,
  endLine: number,
): string {
  return `${repo.url}/blob/HEAD/${path}#L${startLine}-L${endLine}`;
}

export function commitUrl(repo: GitHubRepo, sha: string): string {
  return `${repo.url}/commit/${sha}`;
}
