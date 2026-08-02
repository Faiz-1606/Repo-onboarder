import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface RepoFormProps {
  onSubmit: (repoUrl: string) => void;
  busy: boolean;
  elapsedSeconds: number;
  error: string | null;
}

const EXAMPLE = "https://github.com/pypa/sampleproject.git";

export function RepoForm({ onSubmit, busy, elapsedSeconds, error }: RepoFormProps) {
  const [repoUrl, setRepoUrl] = useState("");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = repoUrl.trim();
    if (trimmed) onSubmit(trimmed);
  };

  return (
    <div className="max-w-2xl">
      <h2 className="text-[15px] font-semibold">Index a repository</h2>
      <p className="mt-1 max-w-lg text-[13px] leading-relaxed text-muted-foreground">
        The code and the commit history are extracted and indexed separately.
        Public repositories only.
      </p>

      <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-2 sm:flex-row">
        <Input
          value={repoUrl}
          onChange={(event) => setRepoUrl(event.target.value)}
          placeholder={EXAMPLE}
          disabled={busy}
          spellCheck={false}
          autoComplete="off"
          className="h-10 flex-1 font-mono text-[13px]"
        />
        <Button type="submit" disabled={busy || !repoUrl.trim()} className="h-10 px-5">
          {busy ? "Indexing..." : "Index"}
        </Button>
      </form>

      {!busy && !error && (
        <button
          type="button"
          onClick={() => setRepoUrl(EXAMPLE)}
          className="mt-3 font-mono text-[12px] text-muted-foreground underline decoration-dotted underline-offset-4 hover:text-foreground"
        >
          use {EXAMPLE}
        </button>
      )}

      {busy && (
        <p className="mt-4 flex items-center gap-2 text-[13px] text-muted-foreground">
          <span
            className="h-1.5 w-1.5 animate-pulse rounded-full"
            style={{ backgroundColor: "hsl(var(--commit-accent))" }}
          />
          Cloning and indexing
          <span className="font-mono tabular-nums">{elapsedSeconds}s</span>
        </p>
      )}

      {error && (
        <div className="mt-4 rounded-sm border border-destructive/40 bg-destructive/10 p-3">
          <p className="font-mono text-[11px] uppercase tracking-wider text-destructive">
            Indexing failed
          </p>
          <p className="mt-1 break-words text-[13px] text-foreground/80">{error}</p>
        </div>
      )}
    </div>
  );
}
