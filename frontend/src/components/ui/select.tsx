import * as React from "react";
import { cn } from "@/lib/utils";

/** Enkel native select med shadcn-utseende (fullt kontrollerbar, sömnsfri). */
export function Select({ className, children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "rounded-lg border border-[color:var(--color-line)] bg-white px-2.5 py-1.5 text-[12.5px] outline-none focus:border-[color:var(--color-accent)]",
        className
      )}
      {...props}
    >
      {children}
    </select>
  );
}

export function Progress({ value, className }: { value: number; className?: string }) {
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-[#e8e3d9]", className)}>
      <div
        className="h-full rounded-full bg-[color:var(--color-accent)] transition-[width] duration-700"
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cn("animate-spin size-5 text-[color:var(--color-accent)]", className)} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}
