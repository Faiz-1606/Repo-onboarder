import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { Conversation, type Turn } from "@/components/Conversation";
import { RepoForm } from "@/components/RepoForm";
import { SessionPanel } from "@/components/SessionPanel";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ask, getIndexStatus, startIndexing, type IndexStats } from "@/lib/api";

const POLL_INTERVAL_MS = 1500;

/* One example per route, so the routing behaviour is discoverable without
   having to read the README first. */
const EXAMPLE_QUESTIONS = [
  "Where is the setup configuration?",
  "Why was the license changed?",
  "How does the build process work?",
];

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
  const bottomRef = useRef<HTMLDivElement>(null);

  // Poll until indexing leaves the "indexing" state. setTimeout is chained
  // after each response rather than setInterval, so a slow reply can never
  // stack up overlapping requests.
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

  // Separate from the poll so the counter moves every second rather than
  // every poll.
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

  return (
    <div className="min-h-screen">
      <header className="bg-grid border-b border-border">
        <div className="mx-auto max-w-5xl px-6 py-8">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-primary">
            Repo Onboarding Assistant
          </p>
          <h1 className="mt-2 max-w-xl text-[26px] font-semibold leading-tight tracking-tight sm:text-[30px]">
            Ask an unfamiliar codebase why, not just where.
          </h1>
          <p className="mt-2.5 max-w-lg text-[13.5px] leading-relaxed text-muted-foreground">
            Code and commit history are indexed as two separate sources. Each
            question is routed to whichever one can actually answer it.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8">
        {phase.name === "ready" ? (
          <div className="flex flex-col gap-8 lg:flex-row">
            <SessionPanel
              repoUrl={phase.repoUrl}
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
                        key={example}
                        type="button"
                        onClick={() => submitQuestion(example)}
                        className="rounded-sm border border-border bg-card px-2.5 py-1.5 text-left text-[12.5px] text-foreground/80 transition-colors hover:border-primary/50 hover:text-foreground"
                      >
                        {example}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <Conversation turns={turns} />
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
        ) : (
          <RepoForm
            onSubmit={beginIndexing}
            busy={phase.name === "indexing"}
            elapsedSeconds={elapsed}
            error={phase.name === "failed" ? phase.error : null}
          />
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
