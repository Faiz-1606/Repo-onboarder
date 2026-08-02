import type { IndexStats } from "@/lib/api";

interface SessionPanelProps {
  repoUrl: string;
  stats: IndexStats;
  elapsedSeconds: number;
  onReset: () => void;
}


export function SessionPanel({
  repoUrl,
  stats,
  elapsedSeconds,
  onReset,
}: SessionPanelProps) {
  const repoName = repoUrl.replace(/^https?:\/\//, "").replace(/\.git$/, "");

  return (
    <aside className="shrink-0 border-border lg:w-64 lg:border-r lg:pr-6">
      <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        Indexed
      </p>
      <p className="mt-1.5 break-all font-mono text-[12.5px] leading-snug text-foreground">
        {repoName}
      </p>

      <dl className="mt-5 space-y-2.5">
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

      <p className="mt-5 font-mono text-[11px] text-muted-foreground">
        indexed in {elapsedSeconds}s
      </p>

      <button
        type="button"
        onClick={onReset}
        className="mt-5 font-mono text-[12px] text-muted-foreground underline decoration-dotted underline-offset-4 hover:text-foreground"
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
