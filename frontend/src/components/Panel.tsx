import type { HTMLAttributes, ReactNode } from "react";
import { clsx } from "clsx";
import type { LucideIcon } from "lucide-react";

interface PanelProps extends HTMLAttributes<HTMLElement> {
  as?: "section" | "div" | "aside";
  padded?: boolean;
  /** `raised`: the one or two surfaces that lead a page (hero, selected station). */
  variant?: "flat" | "raised";
}

/** The one bordered surface. Panels are never nested inside panels; use dividers inside instead. */
export function Panel({ as: Tag = "section", padded = true, variant = "flat", className, children, ...rest }: PanelProps) {
  return (
    <Tag
      className={clsx(
        "min-w-0 rounded-panel border border-line bg-surface",
        variant === "raised" && "shadow-raised",
        padded && "p-4 sm:p-5",
        className,
      )}
      {...rest}
    >
      {children}
    </Tag>
  );
}

interface PanelHeaderProps {
  title: ReactNode;
  id?: string;
  icon?: LucideIcon;
  /** Muted text after the title, e.g. "(water level)". */
  qualifier?: ReactNode;
  /** Optional <InfoTip> shown after the title. */
  info?: ReactNode;
  actions?: ReactNode;
  level?: 2 | 3;
  className?: string;
}

export function PanelHeader({ title, id, icon: Icon, qualifier, info, actions, level = 2, className }: PanelHeaderProps) {
  const H = level === 2 ? "h2" : "h3";
  return (
    <div className={clsx("mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2", className)}>
      <H id={id} className="flex min-w-0 items-center gap-2 text-md font-semibold text-ink">
        {Icon && <Icon aria-hidden className="size-[18px] shrink-0 text-ink-2" />}
        <span>{title}</span>
        {qualifier && <span className="text-sm font-normal text-ink-3">{qualifier}</span>}
      </H>
      {info && <div className="-ml-2 mr-auto">{info}</div>}
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Label/value rows for metadata (definition list). */
export function DefinitionList({ items, className }: { items: { term: ReactNode; value: ReactNode; icon?: LucideIcon }[]; className?: string }) {
  return (
    <dl className={clsx("divide-y divide-line text-sm", className)}>
      {items.map((it, i) => (
        <div key={i} className="flex items-baseline justify-between gap-4 py-2 first:pt-0 last:pb-0">
          <dt className="flex items-center gap-1.5 text-ink-3">
            {it.icon && <it.icon aria-hidden className="size-3.5 shrink-0 text-ink-3" />}
            <span>{it.term}</span>
          </dt>
          <dd className="num text-right font-medium text-ink">{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}
