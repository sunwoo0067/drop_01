import { HTMLAttributes, forwardRef, ReactNode } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { ChevronRight, Home } from "lucide-react";

interface BreadcrumbItem {
    label: string;
    href?: string;
    icon?: ReactNode;
}

interface BreadcrumbProps extends HTMLAttributes<HTMLDivElement> {
    items: BreadcrumbItem[];
}

const Breadcrumb = forwardRef<HTMLDivElement, BreadcrumbProps>(
    ({ items, className, ...props }, ref) => {
        return (
            <nav
                ref={ref}
                className={cn(
                    "flex items-center px-4 py-2 border border-border bg-card/50 backdrop-blur-sm shadow-sm rounded-sm text-[10px] uppercase tracking-widest font-bold font-mono",
                    className
                )}
                {...props}
            >
                <Link
                    href="/"
                    className="flex items-center text-muted-foreground hover:text-primary transition-all hover:scale-110"
                >
                    <Home className="h-3 w-3" />
                </Link>

                {items.map((item, index) => (
                    <div key={index} className="flex items-center">
                        <ChevronRight className="h-2.5 w-2.5 text-muted-foreground/50 mx-2" />
                        {item.href ? (
                            <Link
                                href={item.href}
                                className="flex items-center gap-1 text-muted-foreground hover:text-primary transition-colors"
                            >
                                {item.icon}
                                <span>{item.label}</span>
                            </Link>
                        ) : (
                            <span className="flex items-center gap-1 text-foreground">
                                {item.icon}
                                <span>{item.label}</span>
                            </span>
                        )}
                    </div>
                ))}
            </nav>
        );
    }
);

Breadcrumb.displayName = "Breadcrumb";

export { Breadcrumb };
export type { BreadcrumbItem };
