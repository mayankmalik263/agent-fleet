// Test setup: jest-dom matchers, React Flow browser shims and global mocks.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, vi } from "vitest";
import { navigation } from "./navigation";

// React Flow measures nodes. jsdom has no layout engine, so these shims follow the
// React Flow testing guide (reactflow.dev/learn/advanced-use/testing).
class ResizeObserverMock {
  callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }
  observe(target: Element) {
    setTimeout(() => this.callback([{ target } as ResizeObserverEntry], this as unknown as ResizeObserver), 0);
  }
  unobserve() {}
  disconnect() {}
}

class DOMMatrixReadOnlyMock {
  m22: number;
  constructor(transform: string) {
    const scale = transform?.match(/scale\(([1-9.])\)/)?.[1];
    this.m22 = scale !== undefined ? +scale : 1;
  }
}

globalThis.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;
(globalThis as unknown as { DOMMatrixReadOnly: unknown }).DOMMatrixReadOnly = DOMMatrixReadOnlyMock;
Object.defineProperties(HTMLElement.prototype, {
  offsetHeight: {
    configurable: true,
    get() {
      return parseFloat((this as HTMLElement).style.height) || 1;
    },
  },
  offsetWidth: {
    configurable: true,
    get() {
      return parseFloat((this as HTMLElement).style.width) || 1;
    },
  },
});
(SVGElement.prototype as unknown as { getBBox: () => DOMRect }).getBBox = () =>
  ({ x: 0, y: 0, width: 0, height: 0 }) as DOMRect;
if (!Element.prototype.scrollTo) Element.prototype.scrollTo = () => {};

// next/link needs the Next.js router. A plain anchor is enough for these tests.
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => createElement("a", { href, ...rest }, children),
}));

vi.mock("next/navigation", async () => {
  const { navigation } = await import("./navigation");
  return {
    useSearchParams: () => new URLSearchParams(navigation.search),
    usePathname: () => navigation.pathname,
    useRouter: () => ({ replace: navigation.replace, push: navigation.push, back: () => {}, refresh: () => {} }),
  };
});

afterEach(() => {
  cleanup();
  navigation.search = "";
  navigation.pathname = "/";
  navigation.replace.mockReset();
  navigation.push.mockReset();
  vi.unstubAllGlobals();
});
