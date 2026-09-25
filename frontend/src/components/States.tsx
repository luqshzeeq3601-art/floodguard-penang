import type { ReactNode } from "react";
import { clsx } from "clsx";
import { CircleAlert, CloudOff, Info, OctagonAlert, RefreshCw, TriangleAlert, type LucideIcon } from "lucide-react";
import type { ApiError } from "../api/client";
import { Button } from "./Button";

export function EmptyState({ icon: Icon = Info, title, description, action, className }: { icon?: LucideIcon; title: string; description?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div role="status" className={clsx("flex flex-col items-center justify-center px-4 py-10 text-center", className)}>
      <Icon aria-hidden className="size-5 text-ink-3" />
      <p className="mt-3 text-md font-medium text-ink">{title}</p>
      {description && <p className="mt-1 max-w-[56ch] text-sm text-ink-2">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={clsx("animate-pulse rounded-md bg-sunken", className)} />;
}

export function SkeletonRows({ rows = 6, label }: { rows?: number; label: string }) {
  return (
    <div aria-busy="true" className="space-y-3 py-2">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}

const ERROR_COPY: Record<ApiError["kind"], { title: string; body: string }> = {
  unreachable: { title: "Can't reach the FloodGuard service", body: "The FloodGuard API didn't respond. Check the connection and try again." },
  server: { title: "The FloodGuard service returned an error", body: "The request failed on the server. Try again shortly." },
  not_available: { title: "Not available yet", body: "This capability isn't provided by the FloodGuard API yet." },
};

export function ErrorState({ error, what, onRetry }: { error: ApiError | null; what: string; onRetry?: () => void }) {
  const copy = ERROR_COPY[error?.kind ?? "server"];
  if (error?.kind === "not_available") return <UnavailableFeature title={`${what} not available yet`} />;
  return (
    <EmptyState
      icon={error?.kind === "unreachable" ? CloudOff : CircleAlert}
      title={`Couldn't load ${what.toLowerCase()}`}
      description={copy.body}
      action={onRetry && <Button icon={RefreshCw} onClick={onRetry}>Retry</Button>}
    />
  );
}

/** Gated capability: explains what's missing instead of showing a mock or an empty widget. */
export function UnavailableFeature({ title, description }: { title: string; description?: string }) {
  return (
    <EmptyState
      icon={Info}
      title={title}
      description={description ?? "The FloodGuard API doesn't provide this yet. It will appear here once the backend supports it."}
    />
  );
}

interface QueryLike<T> {
  data: T | undefined;
  error: ApiError | null;
  isPending: boolean;
  refetch: () => unknown;
}

/** Renders loading / error / not-available for a query, and children once data exists. */
export function QueryState<T>({ query, what, loading, children }: { query: QueryLike<T>; what: string; loading?: ReactNode; children: (data: T) => ReactNode }) {
  if (query.data !== undefined) return <>{children(query.data)}</>;
  if (query.isPending) return <>{loading ?? <SkeletonRows label={`Loading ${what.toLowerCase()}`} />}</>;
  return <ErrorState error={query.error} what={what} onRetry={() => void query.refetch()} />;
}

type BannerTone = "info" | "caution" | "danger" | "neutral";
const BANNER: Record<BannerTone, { box: string; icon: LucideIcon; iconClass: string }> = {
  info: { box: "border-primary-line bg-primary-subtle", icon: Info, iconClass: "text-primary" },
  caution: { box: "border-caution/60 bg-caution-subtle", icon: TriangleAlert, iconClass: "text-caution-text" },
  danger: { box: "border-danger/50 bg-danger-subtle", icon: OctagonAlert, iconClass: "text-danger-text" },
  neutral: { box: "border-line bg-subtle", icon: CloudOff, iconClass: "text-ink-2" },
};

export function Banner({ tone, title, children, action, icon }: { tone: BannerTone; title: string; children?: ReactNode; action?: ReactNode; icon?: LucideIcon }) {
  const b = BANNER[tone];
  const Icon = icon ?? b.icon;
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={clsx("flex flex-wrap items-start gap-3 rounded-panel border px-4 py-3", b.box)}>
      <Icon aria-hidden className={clsx("mt-0.5 size-[18px] shrink-0", b.iconClass)} />
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-semibold text-ink">{title}</p>
        {children && <div className="mt-0.5 text-ink-2">{children}</div>}
      </div>
      {action}
    </div>
  );
}
