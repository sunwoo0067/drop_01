import { ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: "primary" | "secondary" | "outline" | "ghost" | "danger";
    size?: "xs" | "sm" | "md" | "lg" | "icon";
    isLoading?: boolean;
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
    ({ className, variant = "primary", size = "md", isLoading, children, disabled, ...props }, ref) => {
        const baseStyles = "inline-flex items-center justify-center rounded-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50";

        const variants = {
            primary: "bg-primary text-primary-foreground hover:bg-primary/90 border border-primary",
            secondary: "bg-secondary text-secondary-foreground hover:bg-muted border border-border",
            outline: "bg-background border border-border hover:bg-muted hover:text-accent-foreground",
            ghost: "hover:bg-muted hover:text-accent-foreground",
            danger: "bg-destructive text-destructive-foreground hover:bg-destructive/90 border border-destructive",
        };

        const sizes = {
            xs: "h-6 px-2 text-[10px]",
            sm: "h-7 px-3 text-xs",
            md: "h-8 px-4 text-sm",
            lg: "h-10 px-6 text-base",
            icon: "h-7 w-7 p-0",
        };

        return (
            <button
                ref={ref}
                className={cn(baseStyles, variants[variant], sizes[size], className)}
                disabled={isLoading || disabled}
                {...props}
            >
                {isLoading && <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />}
                {children}
            </button>
        );
    }
);

Button.displayName = "Button";

export { Button };
