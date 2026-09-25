import { useId, type ReactNode } from "react";
import { clsx } from "clsx";
import { ChevronDown, Search, X, type LucideIcon } from "lucide-react";

const field =
  "h-10 w-full rounded-control border border-line-strong bg-surface text-base text-ink transition-ui " +
  "hover:border-ink-2 focus-visible:border-primary disabled:cursor-not-allowed disabled:bg-sunken disabled:text-ink-disabled max-md:min-h-11";

export interface Option {
  value: string;
  label: string;
  disabled?: boolean;
}

interface SelectProps {
  label: string;
  value: string;
  options: Option[];
  onChange: (value: string) => void;
  /** Visually hide the label (it stays available to assistive tech). */
  hideLabel?: boolean;
  disabled?: boolean;
  className?: string;
}

/** Native select for keyboard, screen-reader and mobile behaviour; styled to the token set. */
export function Select({ label, value, options, onChange, hideLabel = false, disabled, className }: SelectProps) {
  const id = useId();
  return (
    <div className={clsx("min-w-0", className)}>
      <label htmlFor={id} className={clsx("mb-1.5 block text-sm font-medium text-ink-2", hideLabel && "sr-only")}>
        {label}
      </label>
      <div className="relative">
        <select
          id={id}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className={clsx(field, "appearance-none truncate pr-9 pl-3")}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value} disabled={o.disabled}>
              {o.label}
            </option>
          ))}
        </select>
        <ChevronDown aria-hidden className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-ink-3" />
      </div>
    </div>
  );
}

export function SearchInput({ label, value, onChange, placeholder, className }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; className?: string }) {
  const id = useId();
  return (
    <div className={clsx("relative min-w-0", className)}>
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
      <input
        id={id}
        type="search"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className={clsx(field, "pr-9 pl-9 placeholder:text-ink-3 [&::-webkit-search-cancel-button]:hidden")}
      />
      {value && (
        <button
          type="button"
          aria-label="Clear search"
          onClick={() => onChange("")}
          className="absolute top-1/2 right-1.5 inline-flex size-7 -translate-y-1/2 items-center justify-center rounded-md text-ink-3 hover:bg-hover hover:text-ink"
        >
          <X aria-hidden className="size-4" />
        </button>
      )}
    </div>
  );
}

interface Segment<T extends string> {
  value: T;
  label: ReactNode;
  icon?: LucideIcon;
  disabled?: boolean;
  title?: string;
}

/** Mutually exclusive view options (Map | List, 24 h | 3 d, …). Radio-group semantics. */
export function SegmentedControl<T extends string>({ label, value, segments, onChange, size = "md", className }: { label: string; value: T; segments: Segment<T>[]; onChange: (v: T) => void; size?: "sm" | "md"; className?: string }) {
  return (
    <div role="radiogroup" aria-label={label} className={clsx("inline-flex rounded-control border border-line bg-subtle p-1", className)}>
      {segments.map((s) => {
        const selected = s.value === value;
        return (
          <button
            key={s.value}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={s.disabled}
            title={s.title}
            onClick={() => onChange(s.value)}
            onKeyDown={(e) => {
              if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
              e.preventDefault();
              const enabled = segments.filter((x) => !x.disabled);
              const i = enabled.findIndex((x) => x.value === value);
              const next = enabled[(i + (e.key === "ArrowRight" ? 1 : enabled.length - 1)) % enabled.length];
              if (!next) return;
              onChange(next.value);
              const el = e.currentTarget.parentElement?.children[segments.indexOf(next)];
              if (el instanceof HTMLElement) el.focus();
            }}
            tabIndex={selected ? 0 : -1}
            className={clsx(
              "inline-flex items-center gap-2 rounded-[8px] font-medium whitespace-nowrap transition-ui disabled:cursor-not-allowed disabled:text-ink-disabled max-md:min-h-11",
              size === "sm" ? "h-7 px-2.5 text-sm" : "h-8 px-3.5 text-sm",
              selected ? "bg-primary text-white" : "text-ink-2 hover:bg-hover hover:text-ink",
            )}
          >
            {s.icon && <s.icon aria-hidden className="size-4" />}
            {s.label}
          </button>
        );
      })}
    </div>
  );
}

/** Filter tabs with counts ("All (6)", "Bahaya (1)"). Toggle-button semantics. */
export function FilterTabs<T extends string>({
  label,
  value,
  tabs,
  onChange,
}: {
  label: string;
  value: T;
  tabs: { value: T; label: string; count?: number; icon?: LucideIcon }[];
  onChange: (v: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {tabs.map((t) => {
        const selected = t.value === value;
        const Icon = t.icon;
        return (
          <button
            key={t.value}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(t.value)}
            className={clsx(
              "inline-flex h-9 items-center gap-1.5 rounded-control border px-3 text-sm font-medium transition-ui max-md:min-h-11",
              selected
                ? "border-primary-line bg-primary-subtle text-primary-hover shadow-sm"
                : "border-line bg-surface text-ink-2 hover:bg-hover hover:text-ink",
            )}
          >
            {Icon && <Icon aria-hidden className="size-4 shrink-0" />}
            <span>{t.label}</span>
            {t.count !== undefined && <span className="num text-xs opacity-75">({t.count})</span>}
          </button>
        );
      })}
    </div>
  );
}
