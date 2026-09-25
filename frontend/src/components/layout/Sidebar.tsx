import { NavLink } from "react-router";
import { clsx } from "clsx";
import { Bell, ChartLine, Database, House, Info, Map, MapPin, PanelLeftClose, PanelLeftOpen, X, type LucideIcon } from "lucide-react";

const NAV: { to: string; label: string; icon: LucideIcon; end?: boolean }[] = [
  { to: "/", label: "Overview", icon: House, end: true },
  { to: "/map", label: "Live Map", icon: Map },
  { to: "/stations", label: "Stations", icon: MapPin },
  { to: "/predictions", label: "Predictions", icon: ChartLine },
  { to: "/alerts", label: "Alerts", icon: Bell },
  { to: "/status", label: "Data Status", icon: Database },
];

const DISCLAIMER = "Operational prototype. Not an official warning service.";

function BrandMark() {
  return (
    <svg aria-hidden viewBox="0 0 32 32" className="size-9 shrink-0">
      <circle cx="16" cy="16" r="16" className="fill-primary" />
      <path
        d="M7 14c2 0 2-2 4.5-2S14 14 16 14s2-2 4.5-2 2.5 2 4.5 2M7 19c2 0 2-2 4.5-2s2.5 2 4.5 2 2-2 4.5-2 2.5 2 4.5 2"
        fill="none"
        stroke="white"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

interface SidebarProps {
  /** Icon-only rail (tablet default). */
  collapsed: boolean;
  onToggleCollapsed?: () => void;
  /** Rendered inside the mobile drawer. */
  onClose?: () => void;
}

export function Sidebar({ collapsed, onToggleCollapsed, onClose }: SidebarProps) {
  return (
    <div className="flex h-full flex-col">
      <div className={clsx("flex h-20 shrink-0 items-center gap-3", collapsed ? "justify-center px-2" : "px-5")}>
        <BrandMark />
        {!collapsed && (
          <div className="min-w-0 leading-none">
            <p className="text-lg font-bold tracking-tight text-ink">FloodGuard</p>
            <p className="mt-1 text-2xs font-medium tracking-[0.3em] text-ink-2">PENANG</p>
          </div>
        )}
        {onClose && (
          <button type="button" aria-label="Close navigation" onClick={onClose} className="ml-auto inline-flex size-11 items-center justify-center rounded-control text-ink-2 hover:bg-hover">
            <X aria-hidden className="size-5" />
          </button>
        )}
      </div>

      <nav aria-label="Main" className={clsx("flex-1 overflow-y-auto pt-2", collapsed ? "px-2" : "px-3")}>
        <ul className="space-y-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={end}
                onClick={onClose}
                title={collapsed ? label : undefined}
                aria-label={collapsed ? label : undefined}
                className={({ isActive }) =>
                  clsx(
                    "relative flex h-11 items-center gap-3 rounded-control text-base font-medium transition-ui",
                    collapsed ? "justify-center" : "px-3",
                    isActive
                      ? "bg-primary-subtle text-primary-hover font-semibold after:absolute after:inset-y-2.5 after:left-0 after:w-1 after:rounded-r-full after:bg-primary"
                      : "text-ink-2 hover:bg-hover hover:text-ink",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon aria-hidden className={clsx("size-5 shrink-0", isActive && "text-primary")} />
                    {!collapsed && <span>{label}</span>}
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className={clsx("shrink-0 border-t border-line py-4", collapsed ? "px-2" : "px-5")}>
        {onToggleCollapsed && (
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
            title={collapsed ? "Expand navigation" : "Collapse navigation"}
            className={clsx("mb-3 inline-flex h-9 items-center gap-2 rounded-control text-sm text-ink-2 hover:bg-hover hover:text-ink", collapsed ? "w-full justify-center" : "px-2")}
          >
            {collapsed ? <PanelLeftOpen aria-hidden className="size-[18px]" /> : <PanelLeftClose aria-hidden className="size-[18px]" />}
            {!collapsed && "Collapse"}
          </button>
        )}
        <p className={clsx("flex gap-2 text-xs text-ink-3", collapsed && "justify-center")} title={collapsed ? DISCLAIMER : undefined}>
          <Info aria-hidden className="mt-px size-4 shrink-0" />
          <span className={clsx(collapsed && "sr-only")}>{DISCLAIMER}</span>
        </p>
      </div>
    </div>
  );
}
