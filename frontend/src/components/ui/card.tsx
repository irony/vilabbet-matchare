import * as React from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "rounded-[18px] border-[1.5px] border-[color:var(--color-line)] bg-white shadow-[0_1.5px_0_rgba(0,0,0,0.02)]",
        className
      )}
      {...props}
    />
  );
}
export function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex flex-col gap-1.5 p-5 pb-3", className)} {...props} />;
}
export function CardTitle({ className, ...props }: React.ComponentProps<"div">) {
  return <h3 className={cn("text-[17px] font-semibold leading-snug", className)} {...props} />;
}
export function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return <p className={cn("text-[13.5px] text-[color:var(--color-muted)]", className)} {...props} />;
}
export function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("p-5 pt-2", className)} {...props} />;
}
export function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex items-center p-5 pt-0", className)} {...props} />;
}
