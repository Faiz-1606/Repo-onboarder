import { parseAnswer, parseInline } from "@/lib/answer";

/* Renders the answer as React elements rather than injected HTML.
 *
 * The vanilla version had to escape everything by hand before setting
 * innerHTML; building elements sidesteps that class of bug entirely, since
 * React escapes text nodes for us. */
export function AnswerBody({ answer }: { answer: string }) {
  return (
    <div className="space-y-3">
      {parseAnswer(answer).map((block, index) => {
        if (block.kind === "heading") {
          return (
            <h3
              key={index}
              className="pt-1 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground"
            >
              {block.text}
            </h3>
          );
        }

        if (block.kind === "code") {
          return (
            // Long lines scroll inside the block; the page never scrolls
            // sideways. min-w-0 is what lets it shrink inside a flex column.
            <pre
              key={index}
              className="scrollbar-thin min-w-0 overflow-x-auto rounded-sm border border-border bg-background p-3 text-[12.5px] leading-relaxed"
            >
              <code>{block.code}</code>
            </pre>
          );
        }

        return (
          <p
            key={index}
            className="whitespace-pre-wrap break-words text-[14px] leading-relaxed text-foreground/90"
          >
            {parseInline(block.text).map((span, spanIndex) =>
              span.code ? (
                <code
                  key={spanIndex}
                  className="rounded-[3px] bg-secondary px-1 py-0.5 text-[12.5px] text-primary"
                >
                  {span.text}
                </code>
              ) : (
                <span key={spanIndex}>{span.text}</span>
              ),
            )}
          </p>
        );
      })}
    </div>
  );
}
