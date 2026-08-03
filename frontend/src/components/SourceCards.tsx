import { FileCodeIcon, GitCommitIcon } from "@/components/icons";

/* The landing-page explainer.
 *
 * The whole design rests on treating a repository as two knowledge sources, so
 * the interface says that plainly before you have indexed anything - and the
 * colours introduced here are the same ones the route indicator uses later. */
export function SourceCards() {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <SourceCard
        accent="var(--code-accent)"
        icon={<FileCodeIcon className="h-3.5 w-3.5" />}
        label="Code"
        answers="Where is authentication handled?"
        detail="Functions, classes and types, parsed whole with the Python AST and tree-sitter."
      />
      <SourceCard
        accent="var(--commit-accent)"
        icon={<GitCommitIcon className="h-3.5 w-3.5" />}
        label="Commit history"
        answers="Why was this switched to JWT?"
        detail="The reasoning behind a change, which almost never appears in the code itself."
      />
    </div>
  );
}

interface SourceCardProps {
  accent: string;
  icon: React.ReactNode;
  label: string;
  answers: string;
  detail: string;
}

function SourceCard({ accent, icon, label, answers, detail }: SourceCardProps) {
  return (
    <div className="relative overflow-hidden rounded-lg border border-border bg-card p-4">
      {/* A hairline in the source's colour, rather than a coloured panel -
          enough to pair the card with its route badge without shouting. */}
      <span
        className="absolute inset-x-0 top-0 h-px"
        style={{ backgroundColor: `hsl(${accent})` }}
      />

      <div
        className="flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.14em]"
        style={{ color: `hsl(${accent})` }}
      >
        {icon}
        {label}
      </div>

      <p className="mt-3 text-[13.5px] font-medium leading-snug text-foreground">
        &ldquo;{answers}&rdquo;
      </p>
      <p className="mt-2 text-[12.5px] leading-relaxed text-muted-foreground">{detail}</p>
    </div>
  );
}
