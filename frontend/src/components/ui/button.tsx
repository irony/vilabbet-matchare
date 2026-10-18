import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-medium transition-colors focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50 cursor-pointer",
  {
    variants: {
      variant: {
        default: "bg-[color:var(--color-accent)] text-[#f8f7f4] hover:bg-[#102b23] px-7 py-3 text-[15px]",
        outline: "border-[1.5px] border-[color:var(--color-line)] bg-transparent hover:bg-[#eeebe4] px-6 py-3",
        ghost: "hover:bg-[#eeebe4] px-4 py-2",
        link: "underline-offset-4 hover:underline text-[color:var(--color-accent)] p-0 h-auto",
      },
      size: { default: "", sm: "text-[13px] px-4 py-2", lg: "px-8 py-4 text-base", icon: "size-10" },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
export { buttonVariants };
