
export type AnswerBlock =
  | { kind: "heading"; text: string }
  | { kind: "code"; code: string }
  | { kind: "prose"; text: string };

export type InlineSpan = { code: boolean; text: string };


export function parseInline(text: string): InlineSpan[] {
  return text
    .split(/`([^`\n]+)`/g)
    .map((segment, index) => ({ code: index % 2 === 1, text: segment }))
    .filter((span) => span.text.length > 0);
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
