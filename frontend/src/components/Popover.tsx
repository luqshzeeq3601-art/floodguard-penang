import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { clsx } from "clsx";
import { ChevronDown, type LucideIcon } from "lucide-react";
import { buttonClass } from "./buttonClass";

/**
 * Button + anchored panel for secondary controls ("More filters", "Legend").
 * Escape closes and restores focus; outside click closes; focus moves into the panel on open.
 */
export function Popover({ label, icon: Icon, badge, children, align = "right", panelClassName }: { label: string; icon?: LucideIcon; badge?: number; children: ReactNode; align?: "left" | "right"; panelClassName?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    panel.current?.querySelector<HTMLElement>("select, input, button, a")?.focus();
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={root} className="relative">
      <button
        ref={button}
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className={buttonClass("secondary", "md", clsx("text-ink-2", open && "border-primary-line bg-primary-subtle text-primary-hover"))}
      >
        {Icon && <Icon aria-hidden className="size-4" />}
        {label}
        {badge ? <span className="num inline-flex min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs text-white">{badge}</span> : null}
        <ChevronDown aria-hidden className={clsx("size-4 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div
          ref={panel}
          id={id}
          role="group"
          aria-label={label}
          className={clsx(
            "scale-in absolute top-full z-40 mt-2 w-[min(22rem,calc(100vw-2rem))] rounded-panel border border-line bg-surface p-4 shadow-overlay",
            align === "right" ? "right-0" : "left-0",
            panelClassName,
          )}
        >
          {children}
        </div>
      )}
    </div>
  );
}
