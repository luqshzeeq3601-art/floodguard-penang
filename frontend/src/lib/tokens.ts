/**
 * Resolves design tokens (defined in styles/index.css @theme) for SVG attributes, which cannot
 * use CSS var(). The fallbacks mirror the theme and are only used before styles load (tests).
 */
const FALLBACK = {
  "chart-grid": "#eef0f4",
  "chart-axis": "#8891a5",
  "chart-level": "#2563eb",
  "chart-rain": "#0ea5e9",
  "chart-forecast": "#7c3aed",
  "ink-2": "#475569",
  "ink-3": "#64748b",
  "sunken": "#edf0f5",
  caution: "#fbbf24",
  warning: "#f97316",
  danger: "#ef4444",
} as const;

export type ChartToken = keyof typeof FALLBACK;

export function token(name: ChartToken): string {
  if (typeof window === "undefined") return FALLBACK[name];
  const v = getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim();
  return v || FALLBACK[name];
}
