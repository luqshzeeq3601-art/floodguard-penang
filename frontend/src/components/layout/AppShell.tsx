import { useEffect, useRef, useState } from "react";
import { Outlet, useLocation } from "react-router";
import { clsx } from "clsx";
import { Menu } from "lucide-react";
import { Sidebar } from "./Sidebar";
import { StatusStrip } from "./StatusStrip";

const COLLAPSE_KEY = "fg.sidebar.collapsed";

function readCollapsed() {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
    } catch {
      /* storage unavailable: preference is per-session only */
    }
  }, [collapsed]);

  useEffect(() => {
    mainRef.current?.scrollTo({ top: 0 });
  }, [location.pathname]);

  return (
    // Soft-depth shell: neutral canvas → raised, rounded white shell on desktop; full-bleed below lg.
    <div className="h-dvh w-full overflow-hidden bg-canvas lg:p-[clamp(8px,1vw,16px)]">
      <div className="flex h-full w-full overflow-hidden bg-surface lg:rounded-shell lg:shadow-shell">
      <a href="#main" className="sr-only z-50 rounded-control bg-surface px-4 py-2 font-medium text-primary focus:not-sr-only focus:fixed focus:top-3 focus:left-3">
        Skip to main content
      </a>

      {/* Tablet rail */}
      <aside className="hidden h-full w-[72px] shrink-0 border-r border-line bg-sidebar md:block lg:hidden">
        <Sidebar collapsed onToggleCollapsed={() => setDrawerOpen(true)} />
      </aside>
      {/* Desktop sidebar */}
      <aside className={clsx("hidden shrink-0 border-r border-line bg-sidebar transition-[width] duration-150 lg:block", collapsed ? "w-[76px]" : "w-[236px]")}>
        <Sidebar collapsed={collapsed} onToggleCollapsed={() => setCollapsed((c) => !c)} />
      </aside>

      <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
        <div className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-line bg-surface px-2 md:hidden">
          <button
            type="button"
            aria-label="Open navigation"
            onClick={() => setDrawerOpen(true)}
            className="inline-flex size-11 items-center justify-center rounded-control text-ink-2 hover:bg-hover"
          >
            <Menu aria-hidden className="size-5" />
          </button>
          <span className="text-md font-bold text-ink">FloodGuard Penang</span>
        </div>
        <main id="main" ref={mainRef} tabIndex={-1} className="min-w-0 flex-1 outline-none overflow-y-auto">
          <div className="mx-auto w-full max-w-[2200px] px-4 pb-8 sm:px-6 2xl:px-8">
            <StatusStrip />
            <Outlet />
          </div>
        </main>
      </div>
      </div>

      <NavDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  );
}

function NavDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
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
      aria-label="Navigation"
      onClose={onClose}
      onClick={(e) => e.target === e.currentTarget && onClose()}
      className="m-0 h-dvh max-h-dvh w-[280px] max-w-[85vw] border-r border-line bg-sidebar p-0 shadow-overlay backdrop:bg-ink/40"
    >
      {open && <Sidebar collapsed={false} onClose={onClose} />}
    </dialog>
  );
}
