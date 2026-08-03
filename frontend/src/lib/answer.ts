
export type AnswerBlock =
  | { kind: "heading"; text: string }
  | { kind: "code"; code: string }
  | { kind: "prose"; text: string };

export type InlineSpan =
  | { kind: "text"; text: string }
  | { kind: "code"; text: string }
  | { kind: "file"; text: string; path: string; startLine: number; endLine: number }
  | { kind: "commit"; text: string; sha: string };

/* One pass, three alternatives:
 *   `inline code`
 *   path/to/file.py:12-30        a code citation
 *   a1b2c3d4 (                   a commit citation
 *
 * The commit branch requires a following "(" because that is how the API
 * formats one - "a1b2c3d4 (2025-07-07, author)". Without that guard any eight
 * hex characters appearing in prose would become a dead link.
 */
const INLINE_PATTERN =
  /`([^`\n]+)`|([\w./-]+\.[A-Za-z]\w*):(\d+)-(\d+)|\b([0-9a-f]{7,40})\b(?=\s*\()/g;

/** Split prose into code, citations and plain text, keeping source order. */
export function parseInline(text: string): InlineSpan[] {
  const spans: InlineSpan[] = [];
  let cursor = 0;

  for (const match of text.matchAll(INLINE_PATTERN)) {
    const start = match.index ?? 0;
    if (start > cursor) {
      spans.push({ kind: "text", text: text.slice(cursor, start) });
    }

    const [whole, code, path, startLine, endLine, sha] = match;
    if (code !== undefined) {
      spans.push({ kind: "code", text: code });
    } else if (path !== undefined) {
      spans.push({
        kind: "file",
        text: whole,
        path,
        startLine: Number(startLine),
        endLine: Number(endLine),
      });
    } else if (sha !== undefined) {
      spans.push({ kind: "commit", text: whole, sha });
    }

    cursor = start + whole.length;
  }

  if (cursor < text.length) {
    spans.push({ kind: "text", text: text.slice(cursor) });
  }

  return spans.filter((span) => span.text.length > 0);
}

export function parseAnswer(answer: string): AnswerBlock[] {
  const blocks: AnswerBlock[] = [];

  answer.split("```").forEach((section, index) => {
    
    if (index % 2 === 1) {
      const newline = section.indexOf("\n");
      
      const code = (newline === -1 ? section : section.slice(newline + 1)).replace(
        /\n$/,
        "",
      );
      blocks.push({ kind: "code", code });
      return;
    }

   
    let pending: string[] = [];
    const flush = () => {
      const text = pending.join("\n").trim();
      if (text) blocks.push({ kind: "prose", text });
      pending = [];
    };

    for (const line of section.split("\n")) {
      const heading = line.match(/^##\s+(.*)$/);
      if (heading) {
        flush();
        blocks.push({ kind: "heading", text: heading[1] });
      } else {
        pending.push(line);
      }
    }
    flush();
  });

  return blocks;
}
