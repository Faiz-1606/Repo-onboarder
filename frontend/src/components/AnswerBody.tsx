import type { ReactNode } from "react";

import { FileCodeIcon, GitCommitIcon } from "@/components/icons";
import { parseAnswer, parseInline, type InlineSpan } from "@/lib/answer";
import { blobUrl, commitUrl, type GitHubRepo } from "@/lib/github";

interface AnswerBodyProps {
  answer: string;
  /** When known, citations become links back to the source on GitHub. */
  repo: GitHubRepo | null;
}

/* Renders the answer as React elements rather than injected HTML, so there is
   no escaping to get wrong. */
export function AnswerBody({ answer, repo }: AnswerBodyProps) {
  return (
    <div className="space-y-3">
      {parseAnswer(answer).map((block, index) => {
        if (block.kind === "heading") {
          return (
            <h3
              key={index}
              className="flex items-center gap-2 pt-1 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground"
            >
              {block.text}
              <span className="h-px flex-1 bg-border" />
            </h3>
          );
        }

        if (block.kind === "code") {
          return (
            // Long lines scroll inside the block; the page never scrolls
            // sideways. min-w-0 is what lets it shrink inside a flex column.
            <pre
              key={index}
              className="scrollbar-thin min-w-0 overflow-x-auto rounded-md border border-border bg-[hsl(220_20%_4.5%)] p-3.5 text-[12.5px] leading-relaxed"
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
            {parseInline(block.text).map((span, spanIndex) => (
              <Span key={spanIndex} span={span} repo={repo} />
            ))}
          </p>
        );
      })}
    </div>
  );
}

function Span({ span, repo }: { span: InlineSpan; repo: GitHubRepo | null }) {
  if (span.kind === "code") {
    return (
      <code className="rounded-[3px] bg-secondary px-1 py-0.5 text-[12.5px] text-primary">
        {span.text}
      </code>
    );
  }

  if (span.kind === "file") {
    return (
      <Citation
        href={repo ? blobUrl(repo, span.path, span.startLine, span.endLine) : null}
        icon={<FileCodeIcon className="h-3 w-3 shrink-0" />}
        accent="var(--code-accent)"
        title={
          repo
            ? `Open ${span.path} lines ${span.startLine}-${span.endLine} on GitHub`
            : undefined
        }
      >
        {span.text}
      </Citation>
    );
  }

  if (span.kind === "commit") {
    return (
      <Citation
        href={repo ? commitUrl(repo, span.sha) : null}
        icon={<GitCommitIcon className="h-3 w-3 shrink-0" />}
        accent="var(--commit-accent)"
        title={repo ? `Open commit ${span.sha} on GitHub` : undefined}
      >
        {span.text}
      </Citation>
    );
  }

  return <span>{span.text}</span>;
}

interface CitationProps {
  href: string | null;
  icon: ReactNode;
  accent: string;
  title?: string;
  children: ReactNode;
}

/* A citation looks the same whether or not it can link out, so a non-GitHub
   repository still reads clearly - it just has no anchor. */
function Citation({ href, icon, accent, title, children }: CitationProps) {
  const className =
    "inline-flex items-center gap-1 rounded-[3px] border border-border/80 bg-secondary/60 px-1.5 py-px align-baseline font-mono text-[12px]";

  const content = (
    <>
      {icon}
      <span>{children}</span>
    </>
  );

  if (!href) {
    return (
      <span className={className} style={{ color: `hsl(${accent})` }} title={title}>
        {content}
      </span>
    );
  }

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={title}
      className={`${className} transition-colors hover:border-current hover:bg-secondary`}
      style={{ color: `hsl(${accent})` }}
    >
      {content}
    </a>
  );
}
