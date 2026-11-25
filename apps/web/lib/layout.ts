// Hierarchical tree layout for the agent network.
// Parents sit above their children. Each subtree gets a width, and the parent is centred over it.
// The result is deterministic: the same input always gives the same positions.

export interface LayoutItem {
  id: string;
  parentId: string | null;
}

export interface LayoutOptions {
  nodeWidth: number;
  nodeHeight: number;
  /** Horizontal space between sibling subtrees. */
  hGap: number;
  /** Vertical space between levels. */
  vGap: number;
}

export interface Point {
  x: number;
  y: number;
}

export const DEFAULT_LAYOUT: LayoutOptions = { nodeWidth: 248, nodeHeight: 150, hGap: 28, vGap: 64 };

/**
 * Compute top-left positions for each item.
 * Items whose parent is missing become roots. Items in a parent cycle are also made roots,
 * so the function always returns a position for every item.
 */
export function hierarchicalLayout(items: readonly LayoutItem[], options: LayoutOptions = DEFAULT_LAYOUT): Record<string, Point> {
  const { nodeWidth, nodeHeight, hGap, vGap } = options;
  const ids = new Set(items.map((i) => i.id));
  const children = new Map<string, string[]>();
  const roots: string[] = [];

  for (const item of items) {
    const parent = item.parentId && item.parentId !== item.id && ids.has(item.parentId) ? item.parentId : null;
    if (parent) {
      const list = children.get(parent) ?? [];
      list.push(item.id);
      children.set(parent, list);
    } else {
      roots.push(item.id);
    }
  }

  // Find nodes that no root reaches (parent cycles). Promote the first one of each cycle to a root.
  const reached = new Set<string>();
  const mark = (id: string) => {
    const stack = [id];
    while (stack.length) {
      const next = stack.pop() as string;
      if (reached.has(next)) continue;
      reached.add(next);
      for (const child of children.get(next) ?? []) stack.push(child);
    }
  };
  roots.forEach(mark);
  for (const item of items) {
    if (!reached.has(item.id)) {
      roots.push(item.id);
      mark(item.id);
    }
  }

  // Subtree widths. A visited set stops cycles that were broken above.
  const width = new Map<string, number>();
  const measure = (id: string, path: Set<string>): number => {
    const cached = width.get(id);
    if (cached !== undefined) return cached;
    path.add(id);
    const kids = (children.get(id) ?? []).filter((k) => !path.has(k) && !roots.includes(k));
    const kidsWidth = kids.reduce((sum, k) => sum + measure(k, path), 0) + Math.max(0, kids.length - 1) * hGap;
    path.delete(id);
    const w = Math.max(nodeWidth, kidsWidth);
    width.set(id, w);
    return w;
  };

  const positions: Record<string, Point> = {};
  const place = (id: string, left: number, depth: number, path: Set<string>) => {
    if (positions[id]) return;
    const w = measure(id, new Set());
    positions[id] = { x: left + (w - nodeWidth) / 2, y: depth * (nodeHeight + vGap) };
    path.add(id);
    const kids = (children.get(id) ?? []).filter((k) => !path.has(k) && !roots.includes(k));
    const kidsWidth = kids.reduce((sum, k) => sum + measure(k, new Set()), 0) + Math.max(0, kids.length - 1) * hGap;
    let cursor = left + (w - kidsWidth) / 2;
    for (const kid of kids) {
      place(kid, cursor, depth + 1, path);
      cursor += measure(kid, new Set()) + hGap;
    }
    path.delete(id);
  };

  let cursor = 0;
  for (const root of roots) {
    place(root, cursor, 0, new Set());
    cursor += measure(root, new Set()) + hGap * 2;
  }
  return positions;
}

/** Depth-first order of items (parents before children). The timeline uses it for lane order. */
export function hierarchyOrder(items: readonly LayoutItem[]): string[] {
  const ids = new Set(items.map((i) => i.id));
  const children = new Map<string, string[]>();
  const roots: string[] = [];
  for (const item of items) {
    const parent = item.parentId && ids.has(item.parentId) && item.parentId !== item.id ? item.parentId : null;
    if (parent) children.set(parent, [...(children.get(parent) ?? []), item.id]);
    else roots.push(item.id);
  }
  const order: string[] = [];
  const seen = new Set<string>();
  const visit = (id: string) => {
    if (seen.has(id)) return;
    seen.add(id);
    order.push(id);
    for (const kid of children.get(id) ?? []) visit(kid);
  };
  roots.forEach(visit);
  // Items inside parent cycles: add them in input order so every item appears once.
  for (const item of items) visit(item.id);
  return order;
}
