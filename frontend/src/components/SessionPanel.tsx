import { ExternalLinkIcon, GitHubMark } from "@/components/icons";
import type { IndexStats } from "@/lib/api";
import type { GitHubRepo } from "@/lib/github";

interface SessionPanelProps {
  repoUrl: string;
  repo: GitHubRepo | null;
  stats: IndexStats;
  elapsedSeconds: number;
  onReset: () => void;
}

/* What was indexed, kept visible while you ask questions. The two chunk counts
   are the clearest evidence that the repository really is being treated as two
   separate sources. */
export function SessionPanel({
  repoUrl,
  repo,
  stats,
  elapsedSeconds,
  onReset,
}: SessionPanelProps) {
  const fallbackLabel = repoUrl.replace(/^https?:\/\//, "").replace(/\.git$/, "");

  return (
    <aside className="shrink-0 lg:w-[248px]">
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex items-start gap-2.5">
          <GitHubMark className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0">
            {repo ? (
              <>
                <p className="truncate font-mono text-[11.5px] leading-tight text-muted-foreground">
                  {repo.owner}/
                </p>
                <a
                  href={repo.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group inline-flex items-baseline gap-1 font-mono text-[13.5px] font-medium leading-tight hover:text-primary"
                >
                  <span className="break-all">{repo.name}</span>
                  <ExternalLinkIcon className="h-2.5 w-2.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
                </a>
              </>
            ) : (
              <p className="break-all font-mono text-[12.5px] leading-snug">
                {fallbackLabel}
              </p>
            )}
          </div>
        </div>

        <dl className="mt-4 space-y-2.5 border-t border-border pt-4">
          <Stat
            label="code chunks"
            value={stats.code_chunks_indexed}
            accent="var(--code-accent)"
          />
          <Stat
            label="commits"
            value={stats.commit_chunks_indexed}
            accent="var(--commit-accent)"
          />
          <Stat label="files scanned" value={stats.files_seen} />
        </dl>

        <p className="mt-4 font-mono text-[11px] text-muted-foreground">
          indexed in {elapsedSeconds}s
        </p>
      </div>

      <button
        type="button"
        onClick={onReset}
        className="mt-3 px-1 font-mono text-[12px] text-muted-foreground underline decoration-dotted underline-offset-4 transition-colors hover:text-foreground"
      >
        index another repo
      </button>
    </aside>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-[12.5px] text-muted-foreground">{label}</dt>
      <dd
        className="font-mono text-[15px] tabular-nums"
        style={accent ? { color: `hsl(${accent})` } : undefined}
      >
        {value}
      </dd>
    </div>
  );
}
