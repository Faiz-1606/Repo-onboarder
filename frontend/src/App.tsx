import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { Conversation, type Turn } from "@/components/Conversation";
import { GitHubMark } from "@/components/icons";
import { IndexingProgress } from "@/components/IndexingProgress";
import { RepoForm } from "@/components/RepoForm";
import { SessionPanel } from "@/components/SessionPanel";
import { SourceCards } from "@/components/SourceCards";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ask, getIndexStatus, startIndexing, type IndexStats } from "@/lib/api";
import { parseGitHubRepo } from "@/lib/github";

const POLL_INTERVAL_MS = 1500;


// The route each one takes is shown alongside it. These three are chosen to
// hit all three outcomes, so the routing rule is learnable by clicking rather
// than by reading documentation.
const EXAMPLE_QUESTIONS = [
  { text: "Where is the setup configuration?", route: "code" },
  { text: "Why was the license changed?", route: "commits" },
  { text: "How does the build process work?", route: "both" },
] as const;

const ROUTE_ACCENT: Record<string, string> = {
  code: "var(--code-accent)",
  commits: "var(--commit-accent)",
  both: "var(--both-accent)",
};

type Phase =
  | { name: "idle" }
  | { name: "indexing"; sessionId: string; repoUrl: string; startedAt: number }
  | { name: "failed"; error: string }
  | {
      name: "ready";
      sessionId: string;
      repoUrl: string;
      stats: IndexStats;
      elapsedSeconds: number;
    };

export default function App() {
  const [phase, setPhase] = useState<Phase>({ name: "idle" });
  const [elapsed, setElapsed] = useState(0);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  // Only covers the POST /index round trip; once it returns, the phase
  // becomes "indexing" and IndexingProgress takes over.
  const [submitting, setSubmitting] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  
  useEffect(() => {
    if (phase.name !== "indexing") return;

    let cancelled = false;
    let timer = 0;

    const poll = async () => {
      try {
        const status = await getIndexStatus(phase.sessionId);
        if (cancelled) return;

        if (status.status === "indexing") {
          timer = window.setTimeout(poll, POLL_INTERVAL_MS);
          return;
        }
        if (status.status === "failed" || !status.stats) {
          setPhase({ name: "failed", error: status.error ?? "Indexing failed." });
          return;
        }
        setPhase({
          name: "ready",
          sessionId: phase.sessionId,
          repoUrl: phase.repoUrl,
          stats: status.stats,
          elapsedSeconds: Math.round((Date.now() - phase.startedAt) / 1000),
        });
      } catch (error) {
        if (!cancelled) setPhase({ name: "failed", error: (error as Error).message });
      }
    };

    poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [phase]);

  
  useEffect(() => {
    if (phase.name !== "indexing") return;
    const id = window.setInterval(
      () => setElapsed(Math.round((Date.now() - phase.startedAt) / 1000)),
      1000,
    );
    return () => window.clearInterval(id);
  }, [phase]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const beginIndexing = async (repoUrl: string) => {
    setPhase({ name: "idle" });
    setElapsed(0);
    setSubmitting(true);
    try {
      const started = await startIndexing(repoUrl);
      setPhase({
        name: "indexing",
        sessionId: started.session_id,
        repoUrl,
        startedAt: Date.now(),
      });
    } catch (error) {
      setPhase({ name: "failed", error: (error as Error).message });
    } finally {
      setSubmitting(false);
    }
  };

  const submitQuestion = async (text: string) => {
    if (phase.name !== "ready" || asking) return;
    const trimmed = text.trim();
    if (!trimmed) return;

    const id = Date.now();
    setTurns((current) => [
      ...current,
      { id, question: trimmed, reply: null, error: null },
    ]);
    setQuestion("");
    setAsking(true);

    try {
      const reply = await ask(phase.sessionId, trimmed);
      setTurns((current) =>
        current.map((turn) => (turn.id === id ? { ...turn, reply } : turn)),
      );
    } catch (error) {
      setTurns((current) =>
        current.map((turn) =>
          turn.id === id ? { ...turn, error: (error as Error).message } : turn,
        ),
      );
    } finally {
      setAsking(false);
    }
  };

  const reset = () => {
    setPhase({ name: "idle" });
    setTurns([]);
    setQuestion("");
    setElapsed(0);
  };

  // Only used for linking citations back to the source; a non-GitHub repo
  // indexes exactly the same, its citations just stay unlinked.
  const repo = phase.name === "ready" ? parseGitHubRepo(phase.repoUrl) : null;

  return (
    // The grid runs the full page. Panels use an opaque bg-card so they read
    // as sitting on top of it.
    <div className="bg-grid min-h-screen">
      {/* Persistent chrome. The hero below only appears before a repo is
          loaded - once you are working, the header gets out of the way. */}
      <header className="sticky top-0 z-10 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-6 py-3">
          <GitHubMark className="h-4 w-4 shrink-0 text-primary" />
          <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            Repo Onboarding Assistant
          </span>
          {repo && (
            <>
              <span className="text-border">/</span>
              <a
                href={repo.url}
                target="_blank"
                rel="noopener noreferrer"
                className="min-w-0 truncate font-mono text-[12px] hover:text-primary"
              >
                {repo.owner}/{repo.name}
              </a>
            </>
          )}
        </div>
      </header>

      {phase.name !== "ready" && (
        <div className="border-b border-border">
          <div className="mx-auto max-w-5xl px-6 py-10">
            <h1 className="max-w-xl text-[26px] font-semibold leading-tight tracking-tight sm:text-[30px]">
              Ask an unfamiliar codebase why, not just where.
            </h1>
            <p className="mt-2.5 max-w-lg text-[13.5px] leading-relaxed text-muted-foreground">
              Code and commit history are indexed as two separate sources. Each
              question is routed to whichever one can actually answer it, and
              every answer links back to the exact line or commit on GitHub.
            </p>
          </div>
        </div>
      )}

      <main className="mx-auto max-w-5xl px-6 py-8">
        {phase.name === "ready" ? (
          <div className="flex flex-col gap-8 lg:flex-row">
            <SessionPanel
              repoUrl={phase.repoUrl}
              repo={repo}
              stats={phase.stats}
              elapsedSeconds={phase.elapsedSeconds}
              onReset={reset}
            />

            <section className="min-w-0 flex-1">
              {turns.length === 0 ? (
                <div>
                  <p className="text-[13px] text-muted-foreground">
                    Ask anything about this repository. Try one of these:
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {EXAMPLE_QUESTIONS.map((example) => (
                      <button
                        key={example.text}
                        type="button"
                        onClick={() => submitQuestion(example.text)}
                        className="group flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 text-left text-[12.5px] text-foreground/80 transition-colors hover:border-primary/50 hover:text-foreground"
                      >
                        {example.text}
                        <span
                          className="font-mono text-[10px] uppercase tracking-wider opacity-70"
                          style={{ color: `hsl(${ROUTE_ACCENT[example.route]})` }}
                        >
                          {example.route}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <Conversation turns={turns} repo={repo} />
              )}

              <div ref={bottomRef} />

              <Composer
                value={question}
                onChange={setQuestion}
                onSubmit={() => submitQuestion(question)}
                disabled={asking}
              />
            </section>
          </div>
        ) : phase.name === "indexing" ? (
          <IndexingProgress elapsedSeconds={elapsed} />
        ) : (
          <div className="space-y-8">
            <RepoForm
              onSubmit={beginIndexing}
              submitting={submitting}
              error={phase.name === "failed" ? phase.error : null}
            />
            <SourceCards />
          </div>
        )}
      </main>
    </div>
  );
}

interface ComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
}

function Composer({ value, onChange, onSubmit, disabled }: ComposerProps) {
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit();
  };

  // Enter sends, Shift+Enter adds a line - the convention for a chat box.
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  };

  return (
    <form onSubmit={handleSubmit} className="mt-8 border-t border-border pt-5">
      <div className="flex items-end gap-2">
        <Textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
          placeholder="Where is authentication handled?"
          className="min-h-[62px] flex-1 resize-y text-[13.5px]"
        />
        <Button type="submit" disabled={disabled || !value.trim()} className="h-10 px-5">
          Ask
        </Button>
      </div>
      <p className="mt-2 text-[11.5px] text-muted-foreground">
        Enter to send, Shift+Enter for a new line. Every question is answered
        fresh from retrieval - there is no conversation memory.
      </p>
    </form>
  );
}
