import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Link, type LinkProps } from "react-router";
import { clsx } from "clsx";
import { LoaderCircle, type LucideIcon } from "lucide-react";

import { buttonClass, type Size, type Variant } from "./buttonClass";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: LucideIcon;
  loading?: boolean;
  children: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", icon: Icon, loading = false, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      className={buttonClass(variant, size, className)}
      disabled={disabled}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? (
        <LoaderCircle aria-hidden className="size-4 animate-spin" />
      ) : (
        Icon && <Icon aria-hidden className="size-4" />
      )}
      {children}
    </button>
  );
});

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: LucideIcon;
  label: string;
}

/** Icon-only button: always named for assistive tech and mirrored as a tooltip. */
export function IconButton({ icon: Icon, label, className, ...rest }: IconButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={clsx(
        "inline-flex size-9 items-center justify-center rounded-control text-ink-2 transition-ui hover:bg-hover hover:text-ink active:bg-line max-md:size-11",
        className,
      )}
      {...rest}
    >
      <Icon aria-hidden className="size-[18px]" />
    </button>
  );
}

interface ButtonLinkProps extends LinkProps {
  variant?: Variant;
  size?: Size;
  icon?: LucideIcon;
  iconEnd?: LucideIcon;
}

export function ButtonLink({ variant = "secondary", size = "md", icon: Icon, iconEnd: IconEnd, className, children, ...rest }: ButtonLinkProps) {
  return (
    <Link className={buttonClass(variant, size, typeof className === "string" ? className : undefined)} {...rest}>
      {Icon && <Icon aria-hidden className="size-4" />}
      {children as ReactNode}
      {IconEnd && <IconEnd aria-hidden className="size-4" />}
    </Link>
  );
}

/** Inline text link with an optional trailing icon ("View all →"). */
export function TextLink({ className, children, iconEnd: IconEnd, ...rest }: LinkProps & { iconEnd?: LucideIcon }) {
  return (
    <Link
      className={clsx(
        "inline-flex min-h-6 items-center gap-1 rounded-sm text-sm font-medium text-primary transition-ui hover:text-primary-hover hover:underline max-md:min-h-11",
        typeof className === "string" ? className : undefined,
      )}
      {...rest}
    >
      {children as ReactNode}
      {IconEnd && <IconEnd aria-hidden className="size-4" />}
    </Link>
  );
}
