import { HTMLAttributes, forwardRef, ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Search, Settings, User, Bell } from "lucide-react";
import { Input } from "./Input";
import { Button } from "./Button";
import { Badge } from "./Badge";

export interface ToolbarProps extends HTMLAttributes<HTMLDivElement> {
    title?: string;
    subtitle?: string;
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
                    "flex items-center justify-between px-4 py-2 border-b border-border bg-card",
                    className
                )}
                {...props}
            >
                {/* Left: Title, Subtitle, Search */}
                <div className="flex items-center gap-4 flex-1">
                    <div className="flex flex-col">
                        {title && (
                            <h1 className="text-sm font-semibold text-foreground leading-tight">
                                {title}
                            </h1>
                        )}
                        {subtitle && (
                            <span className="text-[10px] text-muted-foreground">
                                {subtitle}
                            </span>
                        )}
                    </div>

                    {showSearch && (
                        <div className="flex-1 max-w-md">
                            <Input
                                type="text"
                                placeholder="검색... (Ctrl+K)"
                                className="text-xs h-7"
                            />
                        </div>
                    )}
                </div>

                {/* Right: Actions, Notification, User Menu */}
                <div className="flex items-center gap-2">
                    {actions}

                    {showNotification && (
                        <Button variant="outline" size="icon" className="h-7 w-7 relative">
                            <Bell className="h-3.5 w-3.5" />
                            {notificationCount > 0 && (
                                <Badge variant="destructive" className="absolute -top-1 -right-1 h-4 w-4 p-0 flex items-center justify-center text-[8px]">
                                    {notificationCount}
                                </Badge>
                            )}
                        </Button>
                    )}

                    {showUserMenu && (
                        <Button variant="outline" size="sm" className="h-7 gap-1.5">
                            <User className="h-3 w-3" />
                            <span className="text-xs">Admin</span>
                        </Button>
                    )}

                    <Button variant="outline" size="icon" className="h-7 w-7">
                        <Settings className="h-3.5 w-3.5" />
                    </Button>
                </div>
            </div>
        );
    }
);

Toolbar.displayName = "Toolbar";

export { Toolbar };
