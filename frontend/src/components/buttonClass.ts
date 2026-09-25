import { clsx } from "clsx";

export type Variant = "primary" | "secondary" | "ghost";
export type Size = "sm" | "md";

const base =
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-control font-medium transition-ui " +
  "disabled:cursor-not-allowed disabled:border-line disabled:bg-sunken disabled:text-ink-disabled aria-disabled:cursor-not-allowed";
const variants: Record<Variant, string> = {
  primary: "bg-primary text-white hover:bg-primary-hover active:bg-primary-active",
  secondary: "border border-line bg-surface text-primary-hover hover:border-primary-line hover:bg-primary-subtle active:bg-primary-line/40",
  ghost: "text-ink-2 hover:bg-hover hover:text-ink active:bg-line",
};
const sizes: Record<Size, string> = {
  sm: "h-9 px-3 text-sm max-md:min-h-11",
  md: "h-10 px-4 text-base max-md:min-h-11",
};

export const buttonClass = (variant: Variant = "secondary", size: Size = "md", extra?: string) =>
  clsx(base, variants[variant], sizes[size], extra);

