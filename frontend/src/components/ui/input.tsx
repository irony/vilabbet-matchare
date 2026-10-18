import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        "flex w-full rounded-xl border-[1.5px] border-[color:var(--color-line)] bg-transparent px-3.5 py-2.5 text-[15px] outline-none transition focus:border-[color:var(--color-accent)] disabled:opacity-50",
        className
      )}
      ref={ref}
      {...props}
    />
  )
);
Input.displayName = "Input";
