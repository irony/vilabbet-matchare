import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[12px] font-semibold border border-transparent",
  {
    variants: {
      variant: {
        default: "bg-[#eeebe4] text-[color:var(--color-ink)]",
        accent: "bg-[color:var(--color-accent-soft)] text-[color:var(--color-accent)]",
        ok: "bg-[color:var(--color-ok-soft)] text-[color:var(--color-ok)]",
        warm: "bg-[color:var(--color-warm-soft)] text-[color:var(--color-warm)]",
        bad: "bg-[color:var(--color-bad-soft)] text-[color:var(--color-bad)]",
        outline: "border-[color:var(--color-line)] text-[color:var(--color-muted)]",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}
export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
export { badgeVariants };
