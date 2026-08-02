import type { Route } from "@/lib/api";
import { cn } from "@/lib/utils";

interface RouteIndicatorProps {
  route: Route;
  codeHits: number;
  commitHits: number;
}

/* Shows which of the two knowledge sources the question was routed to.
 *
 * The distinction that matters: a source is lit because it was *searched*,
 * not because it returned something. "both" with zero commit hits means the
 * history was searched and had nothing - meaningfully different from the
 * history never being consulted, which is what a plain hit count would hide.
 */
export function RouteIndicator({ route, codeHits, commitHits }: RouteIndicatorProps) {
  const searchedCode = route === "code" || route === "both";
  const searchedCommits = route === "commits" || route === "both";

  return (
    <div className="flex items-stretch gap-px overflow-hidden rounded-sm border border-border bg-border text-[11px] font-mono">
      <Segment
        label="code"
        hits={codeHits}
        searched={searchedCode}
        accent="var(--code-accent)"
      />
      <Segment
        label="commits"
        hits={commitHits}
        searched={searchedCommits}
        accent="var(--commit-accent)"
      />
    </div>
  );
}

interface SegmentProps {
  label: string;
  hits: number;
  searched: boolean;
  accent: string;
}

function Segment({ label, hits, searched, accent }: SegmentProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-1.5 bg-card px-2 py-1",
        !searched && "opacity-40",
      )}
      title={
        searched
          ? `${label} searched - ${hits} ${hits === 1 ? "hit" : "hits"}`
          : `${label} not searched for this question`
      }
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{
          backgroundColor: searched ? `hsl(${accent})` : "hsl(var(--muted-foreground))",
        }}
      />
      <span className="uppercase tracking-wider text-muted-foreground">{label}</span>
      <span
        className="tabular-nums"
        style={{ color: searched ? `hsl(${accent})` : undefined }}
      >
        {searched ? hits : "-"}
      </span>
    </div>
  );
}
