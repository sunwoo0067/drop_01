import { HTMLAttributes, forwardRef, ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Settings, User, Bell } from "lucide-react";
import { Input } from "./Input";
import { Button } from "./Button";
import { Badge } from "./Badge";

export interface ToolbarProps extends HTMLAttributes<HTMLDivElement> {
    title?: string;
    subtitle?: string;
    metaItems?: { label: string; value: string }[];
    actions?: ReactNode;
    showSearch?: boolean;
    showNotification?: boolean;
    notificationCount?: number;
    showUserMenu?: boolean;
}

const Toolbar = forwardRef<HTMLDivElement, ToolbarProps>(
    ({
        title,
        subtitle,
        metaItems = [],
        actions,
        showSearch = false,
        showNotification = false,
        notificationCount = 0,
        showUserMenu = true,
        className,
        ...props
    }, ref) => {
        return (
            <div
                ref={ref}
                className={cn(
                    "flex items-center justify-between px-4 py-1.5 border-b border-border bg-card",
                    className
                )}
                {...props}
            >
                {/* Left: Title, Subtitle, Search */}
                <div className="flex items-center gap-4 flex-1">
                    <div className="flex flex-col">
                        {title && (
                            <h1 className="text-base font-semibold text-foreground leading-tight">
                                {title}
                            </h1>
                        )}
                        {subtitle && (
                            <span className="text-xs text-muted-foreground">
                                {subtitle}
                            </span>
                        )}
                        {metaItems.length > 0 && (
                            <div className="mt-1 flex flex-wrap items-center gap-2">
                                {metaItems.map((item, index) => (
                                    <div
                                        key={`${item.label}-${index}`}
                                        className="inline-flex items-center gap-1 rounded-sm border border-border bg-muted/40 px-2 py-0.5 text-[11px]"
                                    >
                                        <span className="uppercase tracking-wider text-muted-foreground">{item.label}</span>
                                        <span className="font-semibold text-foreground">{item.value}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {showSearch && (
                        <div className="flex-1 max-w-md">
                            <Input
                                type="text"
                                placeholder="검색... (Ctrl+K)"
                                size="md"
                            />
                        </div>
                    )}
                </div>

                {/* Right: Actions, Notification, User Menu */}
                <div className="flex items-center gap-2">
                    {actions}

                    {showNotification && (
                        <Button variant="outline" size="icon" className="h-8 w-8 relative">
                            <Bell className="h-4 w-4" />
                            {notificationCount > 0 && (
                                <Badge variant="destructive" className="absolute -top-1 -right-1 h-4 w-4 p-0 flex items-center justify-center text-[8px]">
                                    {notificationCount}
                                </Badge>
                            )}
                        </Button>
                    )}

                    {showUserMenu && (
                        <Button variant="outline" size="sm" className="h-8 gap-1.5">
                            <User className="h-3.5 w-3.5" />
                            <span className="text-sm">Admin</span>
                        </Button>
                    )}

                    <Button variant="outline" size="icon" className="h-8 w-8">
                        <Settings className="h-4 w-4" />
                    </Button>
                </div>
            </div>
        );
    }
);

Toolbar.displayName = "Toolbar";

export { Toolbar };
