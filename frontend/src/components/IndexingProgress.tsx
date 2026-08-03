import { FileCodeIcon, GitCommitIcon } from "@/components/icons";

/* Shown while the background task runs.
 *
 * The two passes are listed separately because that is genuinely what the
 * server is doing - one walk over the source, one over the git log - and
 * naming them makes a slow clone feel like progress rather than a hang.
 *
 * The API reports a single "indexing" status with no sub-steps, so these are
 * presented as work in flight, not as individually completed stages. */
export function IndexingProgress({ elapsedSeconds }: { elapsedSeconds: number }) {
  return (
    <div className="max-w-2xl rounded-lg border border-border bg-card p-5">
      <div className="flex items-center gap-2.5">
        <span
          className="h-2 w-2 animate-pulse rounded-full"
          style={{ backgroundColor: "hsl(var(--commit-accent))" }}
        />
        <p className="text-[13.5px] font-medium">Cloning and indexing</p>
        <span className="ml-auto font-mono text-[12px] tabular-nums text-muted-foreground">
          {elapsedSeconds}s
        </span>
      </div>

      <div className="mt-4 space-y-2.5 border-t border-border pt-4">
        <Pass
          icon={<FileCodeIcon className="h-3.5 w-3.5" />}
          accent="var(--code-accent)"
          label="Parsing source files"
          detail="one chunk per function, class or type"
        />
        <Pass
          icon={<GitCommitIcon className="h-3.5 w-3.5" />}
          accent="var(--commit-accent)"
          label="Reading commit history"
          detail="message, author and changed files per commit"
        />
      </div>

      <p className="mt-4 text-[12px] leading-relaxed text-muted-foreground">
        Each pass is embedded into its own vector collection. A large repository
        with thousands of commits takes longer.
      </p>
    </div>
  );
}

interface PassProps {
  icon: React.ReactNode;
  accent: string;
  label: string;
  detail: string;
}

function Pass({ icon, accent, label, detail }: PassProps) {
  return (
    <div className="flex items-start gap-2.5">
      <span className="mt-0.5 shrink-0" style={{ color: `hsl(${accent})` }}>
        {icon}
      </span>
      <div className="min-w-0">
        <p className="text-[13px] leading-tight">{label}</p>
        <p className="mt-0.5 text-[12px] leading-tight text-muted-foreground">{detail}</p>
      </div>
    </div>
  );
}
