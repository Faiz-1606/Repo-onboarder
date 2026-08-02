import { AnswerBody } from "@/components/AnswerBody";
import { RouteIndicator } from "@/components/RouteIndicator";
import type { ChatReply } from "@/lib/api";

export interface Turn {
  id: number;
  question: string;
  reply: ChatReply | null;
  error: string | null;
}


export function Conversation({ turns }: { turns: Turn[] }) {
  return (
    <div className="space-y-8">
      {turns.map((turn) => (
        <article key={turn.id} className="min-w-0">
          <h2 className="border-l-2 border-primary/60 pl-3 text-[14.5px] font-medium leading-snug">
            {turn.question}
          </h2>

          <div className="mt-3 pl-3">
            {turn.error ? (
              <div className="rounded-sm border border-destructive/40 bg-destructive/10 p-3">
                <p className="break-words text-[13px] text-foreground/80">{turn.error}</p>
              </div>
            ) : turn.reply ? (
              <>
                <RouteIndicator
                  route={turn.reply.route}
                  codeHits={turn.reply.code_hits}
                  commitHits={turn.reply.commit_hits}
                />
                <div className="mt-3">
                  <AnswerBody answer={turn.reply.answer} />
                </div>
              </>
            ) : (
              <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground" />
                Routing and retrieving
              </p>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}
