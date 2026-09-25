import { useState, type ReactNode } from "react";
import { clsx } from "clsx";
import { ChevronDown, type LucideIcon } from "lucide-react";
import { Panel } from "./Panel";

interface CollapsiblePanelProps {
  title: ReactNode;
  icon?: LucideIcon;
  defaultOpen?: boolean;
  children: ReactNode;
  badge?: ReactNode;
  className?: string;
  variant?: "flat" | "raised";
}

export function CollapsiblePanel({
  title,
  icon: Icon,
  defaultOpen = false,
  children,
  badge,
  className,
  variant = "flat",
}: CollapsiblePanelProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <Panel variant={variant} padded={false} className={clsx("overflow-hidden", className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 p-4 text-left transition-ui hover:bg-subtle sm:p-5"
      >
        <div className="flex min-w-0 items-center gap-2 text-md font-semibold text-ink">
          {Icon && <Icon aria-hidden className="size-[18px] shrink-0 text-ink-2" />}
          <span>{title}</span>
          {badge}
        </div>
        <ChevronDown
          aria-hidden
          className={clsx("size-4 shrink-0 text-ink-3 transition-transform duration-200", open && "rotate-180")}
        />
      </button>
      {open && (
        <div className="border-t border-line p-4 fade-in sm:p-5">
          {children}
        </div>
      )}
    </Panel>
  );
}
