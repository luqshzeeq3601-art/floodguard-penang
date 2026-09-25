import type { Tone } from "./status";

/** Literal class names per tone so Tailwind can see them. */
export const TONE: Record<Tone, { dot: string; text: string; solidChip: string; outlineChip: string; subtle: string; bar: string }> = {
  normal: {
    dot: "bg-normal",
    text: "text-normal-text",
    solidChip: "bg-normal-subtle text-normal-text",
    outlineChip: "border-normal text-normal-text",
    subtle: "bg-normal-subtle",
    bar: "bg-normal",
  },
  caution: {
    dot: "bg-caution",
    text: "text-caution-text",
    solidChip: "bg-caution-subtle text-caution-text",
    outlineChip: "border-caution text-caution-text",
    subtle: "bg-caution-subtle",
    bar: "bg-caution",
  },
  warning: {
    dot: "bg-warning",
    text: "text-warning-text",
    solidChip: "bg-warning-subtle text-warning-text",
    outlineChip: "border-warning text-warning-text",
    subtle: "bg-warning-subtle",
    bar: "bg-warning",
  },
  danger: {
    dot: "bg-danger",
    text: "text-danger-text",
    solidChip: "bg-danger-subtle text-danger-text",
    outlineChip: "border-danger text-danger-text",
    subtle: "bg-danger-subtle",
    bar: "bg-danger",
  },
  neutral: {
    dot: "bg-neutral",
    text: "text-neutral-text",
    solidChip: "bg-neutral-subtle text-neutral-text",
    outlineChip: "border-line-strong text-neutral-text",
    subtle: "bg-neutral-subtle",
    bar: "bg-neutral",
  },
  info: {
    dot: "bg-primary",
    text: "text-primary",
    solidChip: "bg-primary-subtle text-primary-hover",
    outlineChip: "border-primary text-primary-hover",
    subtle: "bg-primary-subtle",
    bar: "bg-primary",
  },
};
