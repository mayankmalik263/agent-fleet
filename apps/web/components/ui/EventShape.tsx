import type { CategoryInfo } from "@/lib/events";

/** Small SVG glyph for an event category. The same glyphs appear in the legend and the timeline. */
export function EventShape({ info, size = 10 }: { info: Pick<CategoryInfo, "shape" | "color">; size?: number }) {
  const c = info.color;
  const s = size;
  const h = s / 2;
  let glyph;
  switch (info.shape) {
    case "square":
      glyph = <rect x={1} y={1} width={s - 2} height={s - 2} rx={1.5} fill={c} style={{ fill: c }} />;
      break;
    case "square-outline":
      glyph = <rect x={1.5} y={1.5} width={s - 3} height={s - 3} rx={1.5} fill="none" style={{ stroke: c }} strokeWidth={1.5} />;
      break;
    case "diamond":
      glyph = <polygon points={`${h},0.5 ${s - 0.5},${h} ${h},${s - 0.5} 0.5,${h}`} style={{ fill: c }} />;
      break;
    case "triangle":
      glyph = <polygon points={`${h},0.5 ${s - 0.5},${s - 0.5} 0.5,${s - 0.5}`} style={{ fill: c }} />;
      break;
    case "ring":
      glyph = <circle cx={h} cy={h} r={h - 1.25} fill="none" style={{ stroke: c }} strokeWidth={1.5} />;
      break;
    case "bar":
      glyph = <rect x={h - 1.5} y={0.5} width={3} height={s - 1} rx={1} style={{ fill: c }} />;
      break;
    default:
      glyph = <circle cx={h} cy={h} r={h - 0.5} style={{ fill: c }} />;
  }
  return (
    <svg aria-hidden width={s} height={s} viewBox={`0 0 ${s} ${s}`} className="shrink-0 overflow-visible">
      {glyph}
    </svg>
  );
}
