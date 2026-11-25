import { Fragment, type ReactNode } from "react";

/*
  A small Markdown renderer for agent reports. It makes React elements only (no raw HTML), so text from
  a model cannot inject markup or scripts. Links open only for http, https and mailto URLs.
  Supported: headings, paragraphs, bullet and numbered lists (with nesting), block quotes, fenced code,
  tables, horizontal rules, **bold**, *italic*, `code`, [links](url) and bare URLs.
*/

export type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; ordered: boolean; items: ListItem[] }
  | { kind: "quote"; text: string }
  | { kind: "code"; text: string }
  | { kind: "table"; header: string[]; rows: string[][] }
  | { kind: "rule" };

export interface ListItem {
  text: string;
  children: ListItem[];
}

const LIST_RE = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
const SAFE_URL = /^(https?:\/\/|mailto:)/i;

function isTableDivider(line: string): boolean {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/.test(line);
}

function splitRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => c.trim());
}

/** Parse Markdown text into blocks. Exported for tests. */
export function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    if (/^\s*```/.test(line)) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) body.push(lines[i++]);
      i++;
      blocks.push({ kind: "code", text: body.join("\n") });
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2].replace(/\s+#+\s*$/, "") });
      i++;
      continue;
    }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
      blocks.push({ kind: "rule" });
      i++;
      continue;
    }
    if (line.includes("|") && i + 1 < lines.length && isTableDivider(lines[i + 1])) {
      const header = splitRow(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(splitRow(lines[i++]));
      blocks.push({ kind: "table", header, rows });
      continue;
    }
    if (/^\s*>/.test(line)) {
      const body: string[] = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) body.push(lines[i++].replace(/^\s*>\s?/, ""));
      blocks.push({ kind: "quote", text: body.join(" ") });
      continue;
    }
    const first = LIST_RE.exec(line);
    if (first) {
      const ordered = /\d/.test(first[2]);
      const root: ListItem[] = [];
      const stack: { indent: number; items: ListItem[] }[] = [{ indent: first[1].length, items: root }];
      while (i < lines.length) {
        const m = LIST_RE.exec(lines[i]);
        if (m) {
          const indent = m[1].length;
          const item: ListItem = { text: m[3], children: [] };
          while (stack.length > 1 && indent < stack[stack.length - 1].indent) stack.pop();
          const top = stack[stack.length - 1];
          if (indent > top.indent && top.items.length) {
            const parent = top.items[top.items.length - 1];
            stack.push({ indent, items: parent.children });
          }
          stack[stack.length - 1].items.push(item);
          i++;
        } else if (lines[i].trim() && /^\s{2,}/.test(lines[i])) {
          // Continuation line of the last item.
          const items = stack[stack.length - 1].items;
          if (items.length) items[items.length - 1].text += ` ${lines[i].trim()}`;
          i++;
        } else break;
      }
      blocks.push({ kind: "list", ordered, items: root });
      continue;
    }
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,6})\s/.test(lines[i]) &&
      !/^\s*```/.test(lines[i]) &&
      !/^\s*>/.test(lines[i]) &&
      !LIST_RE.test(lines[i])
    ) {
      para.push(lines[i++].trim());
    }
    blocks.push({ kind: "paragraph", text: para.join(" ") });
  }
  return blocks;
}

const INLINE_RE = /(`[^`]+`)|(\*\*[^*]+\*\*|__[^_]+__)|(\[[^\]]+\]\([^)\s]+\))|(https?:\/\/[^\s)<>\]]+)|(\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g;

function link(href: string, label: ReactNode, key: number): ReactNode {
  if (!SAFE_URL.test(href)) return <Fragment key={key}>{label}</Fragment>;
  return (
    <a key={key} href={href} target="_blank" rel="noreferrer noopener" className="text-primary underline decoration-primary/40 underline-offset-2 hover:decoration-primary">
      {label}
    </a>
  );
}

/** Render inline Markdown. Exported for tests. */
export function renderInline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const m of text.matchAll(INLINE_RE)) {
    const start = m.index ?? 0;
    if (start > last) out.push(text.slice(last, start));
    const [token, code, bold, mdLink, bare, italic] = m;
    if (code) out.push(<code key={key++} className="rounded bg-bg px-1 py-px font-mono text-[0.92em] text-fg">{code.slice(1, -1)}</code>);
    else if (bold) out.push(<strong key={key++} className="font-semibold text-fg">{renderInline(bold.slice(2, -2))}</strong>);
    else if (mdLink) {
      const parts = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(mdLink);
      out.push(parts ? link(parts[2], renderInline(parts[1]), key++) : mdLink);
    } else if (bare) {
      const trimmed = bare.replace(/[.,;:]+$/, "");
      out.push(link(trimmed, trimmed, key++));
      if (trimmed.length < bare.length) out.push(bare.slice(trimmed.length));
    } else if (italic) out.push(<em key={key++}>{renderInline(italic.slice(1, -1))}</em>);
    else out.push(token);
    last = start + token.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function List({ ordered, items }: { ordered: boolean; items: ListItem[] }) {
  const Tag = ordered ? "ol" : "ul";
  return (
    <Tag className={`${ordered ? "list-decimal" : "list-disc"} space-y-1 pl-5 marker:text-fg-3`}>
      {items.map((item, idx) => (
        <li key={idx}>
          {renderInline(item.text)}
          {item.children.length ? <List ordered={ordered} items={item.children} /> : null}
        </li>
      ))}
    </Tag>
  );
}

const HEADING_CLASS = [
  "",
  "text-[18px] font-semibold text-fg mt-1",
  "text-[15px] font-semibold text-fg mt-4 border-b border-line-soft pb-1",
  "text-[13px] font-semibold text-fg mt-3",
  "text-[12px] font-semibold text-fg-2 mt-2 uppercase tracking-wide",
  "text-[12px] font-semibold text-fg-2 mt-2",
  "text-[12px] font-semibold text-fg-3 mt-2",
];

/** Render Markdown text from an agent report as safe React elements. */
export function Markdown({ text, className = "" }: { text: string; className?: string }) {
  const blocks = parseMarkdown(text);
  return (
    <div className={`space-y-2.5 text-[13px] leading-relaxed text-fg-2 ${className}`}>
      {blocks.map((b, idx) => {
        switch (b.kind) {
          case "heading": {
            const Tag = `h${Math.min(6, b.level + 1)}` as "h2";
            return (
              <Tag key={idx} className={HEADING_CLASS[b.level]}>
                {renderInline(b.text)}
              </Tag>
            );
          }
          case "paragraph":
            return <p key={idx}>{renderInline(b.text)}</p>;
          case "list":
            return <List key={idx} ordered={b.ordered} items={b.items} />;
          case "quote":
            return (
              <blockquote key={idx} className="border-l-2 border-primary/60 pl-3 text-fg-2 italic">
                {renderInline(b.text)}
              </blockquote>
            );
          case "code":
            return (
              <pre key={idx} className="overflow-x-auto rounded-md border border-line-soft bg-bg p-2.5 font-mono text-[12px] text-fg">
                {b.text}
              </pre>
            );
          case "table":
            return (
              <div key={idx} className="overflow-x-auto">
                <table className="w-full border-collapse text-[12px]">
                  <thead>
                    <tr>
                      {b.header.map((h, c) => (
                        <th key={c} className="border-b border-line px-2 py-1 text-left font-semibold text-fg">
                          {renderInline(h)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {b.rows.map((row, r) => (
                      <tr key={r} className="odd:bg-panel-2/40">
                        {row.map((cell, c) => (
                          <td key={c} className="border-b border-line-soft px-2 py-1 align-top">
                            {renderInline(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          case "rule":
            return <hr key={idx} className="border-line-soft" />;
        }
      })}
    </div>
  );
}
