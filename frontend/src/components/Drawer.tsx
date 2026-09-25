import { useEffect, useRef, type ReactNode } from "react";

/** Right-side modal drawer on the native <dialog>: focus trap, Escape and backdrop close for free. */
export function Drawer({ open, onClose, label, children }: { open: boolean; onClose: () => void; label: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal?.();
    if (!open && d.open) d.close?.();
  }, [open]);
  return (
    <dialog
      ref={ref}
      aria-label={label}
      onClose={onClose}
      onClick={(e) => e.target === e.currentTarget && onClose()}
      className="slide-in-right m-0 ml-auto h-dvh max-h-dvh w-[min(30rem,100vw)] max-w-full border-l border-line bg-surface p-5 shadow-overlay backdrop:bg-ink/40 sm:p-6"
    >
      {open && children}
    </dialog>
  );
}
