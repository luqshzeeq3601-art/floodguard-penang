import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { clsx } from "clsx";
import { Info } from "lucide-react";

/**
 * Click-to-open explanation. Replaces repeated grey helper sentences so panels stay data-only.
 * Keyboard: Enter/Space toggles, Escape closes and returns focus; outside click closes.
 */
export function InfoTip({ label, children, align = "left", className }: { label: string; children: ReactNode; align?: "left" | "right"; className?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLSpanElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
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
    <span ref={root} className={clsx("relative inline-flex align-middle", className)}>
      <button
        ref={button}
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex size-6 items-center justify-center rounded-full text-ink-3 transition-ui hover:bg-hover hover:text-ink aria-expanded:text-primary"
      >
        <Info aria-hidden className="size-4" />
      </button>
      {open && (
        <span
          id={id}
          role="note"
          className={clsx(
            "scale-in absolute top-full z-40 mt-1.5 block w-72 max-w-[80vw] rounded-control border border-line bg-surface p-3 text-left text-sm font-normal text-ink-2 shadow-pop",
            align === "right" ? "right-0" : "left-0",
          )}
        >
          {children}
        </span>
      )}
    </span>
  );
}
