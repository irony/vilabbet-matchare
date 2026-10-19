import type { ReactNode } from "react";

/** Minimal markdown-renderare för agentsvar: **fet**, *kursiv*, `kod`,
 *  punkt-/nummerlistor och stycken — räcker långt och utan beroenden. */

const INLINE = /(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/g;

function inline(text: string, keyBase: string): ReactNode[] {
  return text
    .split(INLINE)
    .filter(Boolean)
    .map((part, i) => {
      const k = `${keyBase}-${i}`;
      if (part.startsWith("**") && part.endsWith("**"))
        return <strong key={k} className="font-semibold text-[color:var(--color-ink)]">{part.slice(2, -2)}</strong>;
      if (part.startsWith("*") && part.endsWith("*") && part.length > 2)
        return <em key={k}>{part.slice(1, -1)}</em>;
      if (part.startsWith("`") && part.endsWith("`"))
        return <code key={k} className="rounded bg-[color:var(--color-accent-soft)] px-1 py-0.5 font-mono text-[12px]">{part.slice(1, -1)}</code>;
      return <span key={k}>{part}</span>;
    });
}

export default function Markdown({ text, className }: { text: string; className?: string }) {
  const blocks: ReactNode[] = [];
  let para: string[] = [];
  let lista: string[] = [];
  let n = 0;

  const flushPara = () => {
    if (!para.length) return;
    const t = para.join("\n");
    blocks.push(
      <p key={`p${n++}`} className="whitespace-pre-wrap">
        {inline(t, `p${n}`)}
      </p>,
    );
    para = [];
  };
  const flushLista = () => {
    if (!lista.length) return;
    blocks.push(
      <ul key={`u${n++}`} className="ml-4 list-disc space-y-1">
        {lista.map((item, j) => (
          <li key={j}>{inline(item, `l${n}-${j}`)}</li>
        ))}
      </ul>,
    );
    lista = [];
  };

  for (const rad of text.split("\n")) {
    const trimmad = rad.trim();
    if (/^[-•*]\s+/.test(trimmad)) {
      flushPara();
      lista.push(trimmad.replace(/^[-•*]\s+/, ""));
    } else if (/^\d+[.)]\s+/.test(trimmad)) {
      flushPara();
      lista.push(trimmad.replace(/^\d+[.)]\s+/, ""));
    } else if (!trimmad) {
      flushLista();
      flushPara();
    } else {
      flushLista();
      para.push(rad);
    }
  }
  flushLista();
  flushPara();

  return <div className={className}>{blocks}</div>;
}
