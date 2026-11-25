// Navigation state for the next/navigation mock. Tests change it before they render.
import { vi } from "vitest";

export const navigation = {
  search: "",
  pathname: "/",
  replace: vi.fn(),
  push: vi.fn(),
};
