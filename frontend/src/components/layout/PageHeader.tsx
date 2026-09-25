import type { ReactNode } from "react";
import { Link } from "react-router";
import { clsx } from "clsx";
import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, RefreshCw } from "lucide-react";
import { Button } from "../Button";
import { TimeLabel } from "../Measurement";

interface PageHeaderProps {
  title: string;
  subtitle?: ReactNode;
  breadcrumb?: { label: string; to?: string }[];
  /** When the page last received data from the API (epoch ms). */
  updatedAt?: number;
  updatedLabel?: string;
  /** Contextual selector(s), e.g. district or time range. */
  children?: ReactNode;
  meta?: ReactNode;
}

export function PageHeader({ title, subtitle, breadcrumb, updatedAt, updatedLabel = "Last updated", children, meta }: PageHeaderProps) {
  const qc = useQueryClient();
  const fetching = useIsFetching() > 0;
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4 pt-5 pb-5 lg:pt-6">
      <div className="min-w-0">
        {breadcrumb && (
          <nav aria-label="Breadcrumb" className="mb-2">
            <ol className="flex flex-wrap items-center gap-1 text-sm text-ink-2">
              {breadcrumb.map((b, i) => (
                <li key={b.label} className="flex items-center gap-1">
                  {i > 0 && <ChevronRight aria-hidden className="size-4 text-ink-3" />}
                  {b.to ? (
                    <Link to={b.to} className="rounded-sm hover:text-primary hover:underline">
                      {b.label}
                    </Link>
                  ) : (
                    <span aria-current="page" className="font-medium text-ink">
                      {b.label}
                    </span>
                  )}
                </li>
              ))}
            </ol>
          </nav>
        )}
        <h1 className="text-title font-bold tracking-tight text-balance text-ink">{title}</h1>
        {subtitle && <div className="mt-1 text-base text-ink-2">{subtitle}</div>}
        {meta && <div className="mt-3">{meta}</div>}
      </div>
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        {updatedAt ? (
          <div className="flex items-center gap-2 rounded-control bg-subtle px-3 py-1.5 border border-line/60">
            <span className="relative flex size-2">
              <span className={clsx("absolute inline-flex h-full w-full rounded-full opacity-75", fetching ? "animate-ping bg-primary" : "bg-normal")} />
              <span className={clsx("relative inline-flex size-2 rounded-full", fetching ? "bg-primary" : "bg-normal")} />
            </span>
            <p className="text-xs font-medium text-ink-2">
              <span className="max-sm:hidden">
                {fetching ? "Syncing..." : `${updatedLabel}: `}
                <TimeLabel iso={new Date(updatedAt).toISOString()} full />
              </span>
              <span className="sm:hidden">
                <TimeLabel iso={new Date(updatedAt).toISOString()} />
              </span>
            </p>
          </div>
        ) : null}
        <Button icon={RefreshCw} loading={fetching} size="md" onClick={() => void qc.invalidateQueries()} className="shadow-2xs">
          Refresh
        </Button>
        {children}
      </div>
    </header>
  );
}
