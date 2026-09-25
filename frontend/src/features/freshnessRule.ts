import type { FreshnessRule } from "../api/types";
import { formatDuration } from "../lib/format";
import { FRESHNESS } from "../lib/status";

/** Human text for a freshness state, using the API-served rule when available. */
export function freshnessRuleText(f: keyof typeof FRESHNESS, rule?: FreshnessRule) {
  if (!rule) return FRESHNESS[f].description;
  switch (f) {
    case "FRESH":
      return `Observation ≤ ${formatDuration(rule.fresh_max_minutes)} old.`;
    case "DELAYED":
      return `Older than ${formatDuration(rule.fresh_max_minutes)}, up to ${formatDuration(rule.stale_after_minutes)}.`;
    case "STALE":
      return `Older than ${formatDuration(rule.stale_after_minutes)}.`;
    default:
      return FRESHNESS[f].description;
  }
}

