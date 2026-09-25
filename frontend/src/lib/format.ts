/** The only place numbers, units and times are formatted. All times render in Malaysia time. */

const TZ = "Asia/Kuala_Lumpur";

const dayKey = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const timeFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const shortFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});
const fullFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ, day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});
const dateFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "numeric", month: "short", year: "numeric" });

const toDate = (iso: string) => new Date(iso);
/** en-GB renders September as "Sept"; normalise to the three-letter form used everywhere else. */
const sep = (s: string) => s.replace("Sept", "Sep");
const valid = (d: Date) => !Number.isNaN(d.getTime());

/** `01:45` today, `23 Sep, 15:15` otherwise. */
export function formatTime(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "—";
  const d = toDate(iso);
  if (!valid(d)) return "—";
  return dayKey.format(d) === dayKey.format(now) ? timeFmt.format(d) : sep(shortFmt.format(d).replace(" at ", ", "));
}

/** `24 Sep 2026, 01:45 MYT`. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = toDate(iso);
  return valid(d) ? `${sep(fullFmt.format(d).replace(" at ", ", "))} MYT` : "—";
}

export function formatDate(iso: string): string {
  const d = toDate(iso);
  return valid(d) ? sep(dateFmt.format(d)) : "—";
}

export function formatClock(iso: string): string {
  const d = toDate(iso);
  return valid(d) ? timeFmt.format(d) : "—";
}

/** Minutes → `15 min`, `10 h 30 min`, `2 d 4 h`. */
export function formatDuration(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || minutes < 0) return "—";
  if (minutes < 60) return `${Math.round(minutes)} min`;
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (h < 24) return m ? `${h} h ${m} min` : `${h} h`;
  const d = Math.floor(h / 24);
  const rh = h % 24;
  return rh ? `${d} d ${rh} h` : `${d} d`;
}

export function formatAge(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "—";
  if (minutes < 1) return "just now";
  return `${formatDuration(minutes)} ago`;
}

export const THIN = " ";

/** Water level in metres, 2 dp. Missing is `—`, never 0. */
export const formatMetres = (v: number | null | undefined) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${v.toFixed(2)}${THIN}m`;

/** Rainfall in mm, 1 dp. Zero rainfall is a real value and shows as `0.0 mm`. */
export const formatMm = (v: number | null | undefined) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${v.toFixed(1)}${THIN}mm`;

export const formatSignedMetres = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(2)}${THIN}m`;

/** Model probability → integer percent; avoids false precision. */
export const formatProbability = (p: number | null | undefined) =>
  p === null || p === undefined ? "—" : `${Math.round(p * 100)}%`;

export const formatPercent = (part: number, whole: number) =>
  whole > 0 ? `${Math.round((part / whole) * 100)}%` : "—";

export const formatHorizon = (minutes: number) => `${minutes} min`;

/** Bare number for unit-labelled table columns. Missing is `—`. */
export const formatNumber = (v: number | null | undefined, dp: number) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(dp);

/** Day group label in MYT: "Today", "Yesterday" or "23 Sep 2026". */
export function formatDayLabel(iso: string, now: Date = new Date()): string {
  const d = toDate(iso);
  if (!valid(d)) return "—";
  const key = dayKey.format(d);
  if (key === dayKey.format(now)) return "Today";
  if (key === dayKey.format(new Date(now.getTime() - 86_400_000))) return "Yesterday";
  return formatDate(iso);
}
