import { useState, type FormEvent } from "react";

import { GitHubMark } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface RepoFormProps {
  onSubmit: (repoUrl: string) => void;
  submitting: boolean;
  error: string | null;
}

// Verified small: 197 commits, indexes in a few seconds. Deliberately not a
// large repository - a first run that takes two minutes reads as broken.
const EXAMPLE = "https://github.com/pypa/sampleproject.git";

export function RepoForm({ onSubmit, submitting, error }: RepoFormProps) {
  const [repoUrl, setRepoUrl] = useState("");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = repoUrl.trim();
    if (trimmed) onSubmit(trimmed);
  };

  return (
    <div className="max-w-2xl">
      <form onSubmit={handleSubmit}>
        <label
          htmlFor="repo-url"
          className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-muted-foreground"
        >
          Public repository URL
        </label>

        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <GitHubMark className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="repo-url"
              value={repoUrl}
              onChange={(event) => setRepoUrl(event.target.value)}
              placeholder="github.com/owner/repo"
              disabled={submitting}
              spellCheck={false}
              autoComplete="off"
              className="h-10 w-full pl-9 font-mono text-[13px]"
            />
          </div>
          <Button
            type="submit"
            disabled={submitting || !repoUrl.trim()}
            className="h-10 px-5"
          >
            {submitting ? "Starting..." : "Index"}
          </Button>
        </div>
      </form>

      <button
        type="button"
        onClick={() => setRepoUrl(EXAMPLE)}
        className="mt-2.5 font-mono text-[11.5px] text-muted-foreground underline decoration-dotted underline-offset-4 transition-colors hover:text-foreground"
      >
        try pypa/sampleproject
      </button>

      {error && (
        <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 p-3">
          <p className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-destructive">
            Indexing failed
          </p>
          <p className="mt-1.5 break-words text-[13px] leading-relaxed text-foreground/80">
            {error}
          </p>
        </div>
      )}
    </div>
  );
}
