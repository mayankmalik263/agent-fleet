// Readable lines from a run's usage_json. Only values that the API reports are shown.
import { formatCount, humanize } from "./format";
import type { JsonObject } from "./types";

export interface UsageLine {
  label: string;
  value: string;
}

function isObject(value: unknown): value is JsonObject {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

/** Flatten usage_json one level deep into label and value pairs. Costs are labelled as estimates. */
export function usageLines(usage: JsonObject | null | undefined): UsageLine[] {
  if (!usage) return [];
  const lines: UsageLine[] = [];
  const add = (key: string, value: unknown) => {
    if (typeof value === "number" && Number.isFinite(value)) {
      if (key.toLowerCase().includes("cost")) {
        lines.push({ label: "Estimated cost (client-side)", value: `$${value.toFixed(4)}` });
      } else {
        lines.push({ label: humanize(key), value: formatCount(value) });
      }
    } else if (typeof value === "string" && value && value.length <= 40) {
      lines.push({ label: humanize(key), value });
    }
  };
  for (const [key, value] of Object.entries(usage)) {
    if (isObject(value)) for (const [k, v] of Object.entries(value)) add(k, v);
    else add(key, value);
  }
  return lines;
}
