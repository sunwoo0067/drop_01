import { InputHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
    error?: boolean;
    size?: "xs" | "sm" | "md";
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
    ({ className, type, error, size = "md", ...props }, ref) => {
        const sizes = {
            xs: "h-6 px-2 text-xs py-1",
            sm: "h-7 px-2.5 text-xs py-1.5",
            md: "h-8 px-3 text-sm py-2",
        };

        return (
            <input
                type={type}
                className={cn(
                    "flex w-full rounded-sm border border-border bg-background file:border-0 file:bg-transparent file:text-xs file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50",
                    sizes[size],
                    error && "border-destructive focus-visible:ring-destructive",
                    className
                )}
                ref={ref}
                {...props}
            />
        );
    }
);
Input.displayName = "Input";
