import { Fragment, useMemo, useState, type ReactNode } from "react";
import { clsx } from "clsx";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight } from "lucide-react";

export interface Column<T> {
  key: string;
  header: ReactNode;
  cell: (row: T, index: number) => ReactNode;
  /** Enables sorting on this column. */
  sortValue?: (row: T) => string | number;
  align?: "left" | "right";
  /** Hide below this breakpoint (the mobile card still shows the data). */
  hideBelow?: "xl" | "2xl" | "3xl";
  className?: string;
}

interface DataTableProps<T> {
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  selectedKey?: string | null;
  /** Mouse convenience; every row must also contain a focusable link or button. */
  onRowClick?: (row: T) => void;
  /** Compact card used below the `md` breakpoint instead of the table. */
  mobileCard?: (row: T, index: number) => ReactNode;
  empty?: ReactNode;
  pageSize?: number;
  initialSort?: { key: string; dir: "asc" | "desc" };
  footer?: ReactNode;
  stickyHeader?: boolean;
  /** Inserts a group header row whenever this key changes between consecutive visible rows. */
  groupBy?: (row: T) => string;
}

const hide = { xl: "max-xl:hidden", "2xl": "max-2xl:hidden", "3xl": "max-3xl:hidden" } as const;

export function DataTable<T>({ caption, columns, rows, rowKey, selectedKey, onRowClick, mobileCard, empty, pageSize, initialSort, footer, stickyHeader = true, groupBy }: DataTableProps<T>) {
  const [sort, setSort] = useState(initialSort ?? null);
  const [page, setPage] = useState(0);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    const get = col.sortValue;
    const out = [...rows].sort((a, b) => {
      const va = get(a);
      const vb = get(b);
      return typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb));
    });
    return sort.dir === "desc" ? out.reverse() : out;
  }, [rows, sort, columns]);

  const pages = pageSize ? Math.max(1, Math.ceil(sorted.length / pageSize)) : 1;
  const current = Math.min(page, pages - 1);
  const visible = pageSize ? sorted.slice(current * pageSize, (current + 1) * pageSize) : sorted;
  const offset = pageSize ? current * pageSize : 0;

  const toggleSort = (key: string) => {
    setPage(0);
    setSort((s) => (s?.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" }));
  };

  if (rows.length === 0) return <>{empty}</>;

  return (
    <div className="min-w-0">
      {mobileCard && (
        <ul aria-label={caption} className="divide-y divide-line md:hidden">
          {visible.map((r, i) => (
            <li key={rowKey(r)} className={clsx(selectedKey === rowKey(r) && "bg-primary-subtle")}>
              {mobileCard(r, offset + i)}
            </li>
          ))}
        </ul>
      )}
      <div className={clsx("overflow-x-auto", mobileCard && "max-md:hidden")}>
        <table className="w-full border-separate border-spacing-0 text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              {columns.map((c) => {
                const active = sort?.key === c.key;
                const SortIcon = active ? (sort!.dir === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
                return (
                  <th
                    key={c.key}
                    scope="col"
                    aria-sort={active ? (sort!.dir === "asc" ? "ascending" : "descending") : undefined}
                    className={clsx(
                      "h-10 border-y border-line bg-subtle px-3 text-xs font-medium whitespace-nowrap text-ink-3 first:rounded-l-control first:border-l first:pl-4 last:rounded-r-control last:border-r",
                      stickyHeader && "sticky top-0 z-10",
                      c.align === "right" ? "text-right" : "text-left",
                      c.hideBelow && hide[c.hideBelow],
                    )}
                  >
                    {c.sortValue ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(c.key)}
                        className={clsx("group inline-flex items-center gap-1 rounded-sm hover:text-ink", active && "text-ink", c.align === "right" && "flex-row-reverse")}
                      >
                        {c.header}
                        <SortIcon aria-hidden className={clsx("size-3.5", !active && "opacity-40 group-hover:opacity-100 group-focus-visible:opacity-100")} />
                      </button>
                    ) : (
                      c.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visible.map((r, i) => {
              const key = rowKey(r);
              const selected = selectedKey === key;
              const group = groupBy?.(r);
              const newGroup = group !== undefined && (i === 0 || groupBy!(visible[i - 1]!) !== group);
              return (
                <Fragment key={key}>
                {newGroup && (
                  <tr>
                    <th colSpan={columns.length} scope="colgroup" className="bg-surface px-4 pt-4 pb-1.5 text-left text-xs font-semibold text-ink-2">
                      {group}
                    </th>
                  </tr>
                )}
                <tr
                  aria-selected={selectedKey !== undefined ? selected : undefined}
                  onClick={onRowClick ? () => onRowClick(r) : undefined}
                  className={clsx(
                    "group transition-ui",
                    onRowClick && "cursor-pointer",
                    selected ? "bg-primary-subtle" : "hover:bg-subtle",
                  )}
                >
                  {columns.map((c, ci) => (
                    <td
                      key={c.key}
                      className={clsx(
                        "h-12 border-b border-line px-3 py-2 align-middle text-ink",
                        ci === 0 && "pl-4",
                        ci === 0 && selected && "shadow-[inset_2px_0_0_var(--color-primary)]",
                        c.align === "right" && "num text-right",
                        c.hideBelow && hide[c.hideBelow],
                        c.className,
                      )}
                    >
                      {c.cell(r, offset + i)}
                    </td>
                  ))}
                </tr>
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {(pageSize || footer) && (
        <div className="flex flex-wrap items-center justify-between gap-3 pt-4 text-sm text-ink-2">
          <p className="num" aria-live="polite">
            Showing {offset + 1}–{offset + visible.length} of {sorted.length}
          </p>
          {footer}
          {pageSize && pages > 1 && (
            <nav aria-label={`${caption} pages`} className="flex items-center gap-1">
              <PageButton label="Previous page" disabled={current === 0} onClick={() => setPage(current - 1)}>
                <ChevronLeft aria-hidden className="size-4" />
              </PageButton>
              {Array.from({ length: pages }, (_, p) => (
                <PageButton key={p} label={`Page ${p + 1}`} current={p === current} onClick={() => setPage(p)}>
                  {p + 1}
                </PageButton>
              ))}
              <PageButton label="Next page" disabled={current === pages - 1} onClick={() => setPage(current + 1)}>
                <ChevronRight aria-hidden className="size-4" />
              </PageButton>
            </nav>
          )}
        </div>
      )}
    </div>
  );
}

function PageButton({ label, current, disabled, onClick, children }: { label: string; current?: boolean; disabled?: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-current={current ? "page" : undefined}
      disabled={disabled}
      onClick={onClick}
      className={clsx(
        "num inline-flex size-9 items-center justify-center rounded-control border text-sm font-medium transition-ui disabled:cursor-not-allowed disabled:text-ink-disabled max-md:size-11",
        current ? "border-primary bg-primary text-white" : "border-line bg-surface text-ink-2 hover:bg-hover",
      )}
    >
      {children}
    </button>
  );
}
