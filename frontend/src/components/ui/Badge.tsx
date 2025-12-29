import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends HTMLAttributes<HTMLDivElement> {
    variant?: "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "primary";
    weight?: "subtle" | "solid";
}

function Badge({ className, variant = "default", weight = "subtle", ...props }: BadgeProps) {
    const isSubtle = weight === "subtle";

    const variants = {
        default: isSubtle ? "border border-border bg-secondary text-foreground" : "bg-foreground text-background",
        secondary: isSubtle ? "border border-border bg-muted text-muted-foreground" : "bg-muted-foreground text-muted",
        primary: isSubtle ? "border border-primary/20 bg-primary/10 text-primary" : "bg-primary text-primary-foreground",
        destructive: isSubtle ? "border border-destructive/20 bg-destructive/10 text-destructive" : "bg-destructive text-destructive-foreground",
        outline: "border border-border bg-transparent text-foreground",
        success: isSubtle ? "border border-success/20 bg-success/10 text-success" : "bg-success text-success-foreground",
        warning: isSubtle ? "border border-warning/20 bg-warning/10 text-warning" : "bg-warning text-warning-foreground",
        info: isSubtle ? "border border-info/20 bg-info/10 text-info" : "bg-info text-info-foreground",
    };

    return (
        <div className={cn("inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-tight", variants[variant], className)} {...props} />
    );
}

export { Badge };
