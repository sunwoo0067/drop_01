"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, ShoppingBag, Search, Settings, Bot, Menu, X } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";

const menuItems = [
    { name: "대시보드", href: "/", icon: LayoutDashboard },
    { name: "상품 관리", href: "/products", icon: ShoppingBag },
    { name: "상품 소싱", href: "/sourcing", icon: Search },
    { name: "벤치마크", href: "/benchmarks", icon: Search },
    { name: "공급사 상품수집", href: "/suppliers", icon: Search },
    { name: "공급사 상품목록", href: "/suppliers/items", icon: ShoppingBag },
    { name: "에이전트", href: "/agents", icon: Bot },
    { name: "설정", href: "/settings", icon: Settings },
];

export default function Sidebar() {
    const pathname = usePathname();
    const [collapsed, setCollapsed] = useState(false);

    return (
        <div className={cn(
            "flex flex-col border-r bg-card h-screen transition-all duration-300 ease-in-out",
            collapsed ? "w-16" : "w-64"
        )}>
            <div className="flex h-16 items-center border-b px-4 justify-between">
                {!collapsed && <h1 className="text-xl font-bold text-primary">DropAutomata</h1>}
                <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setCollapsed(!collapsed)}
                    className="ml-auto"
                >
                    {collapsed ? <Menu className="h-4 w-4" /> : <X className="h-4 w-4" />}
                </Button>
            </div>

            <nav className="flex-1 space-y-1 p-2">
                {menuItems.map((item) => {
                    const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={cn(
                                "group flex items-center rounded-md px-3 py-2 text-sm font-medium transition-colors mb-1",
                                isActive
                                    ? "bg-primary/10 text-primary"
                                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                                collapsed && "justify-center px-2"
                            )}
                        >
                            <item.icon
                                className={cn(
                                    "h-5 w-5 flex-shrink-0 transition-colors",
                                    isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
                                    !collapsed && "mr-3"
                                )}
                            />
                            {!collapsed && <span>{item.name}</span>}
                        </Link>
                    );
                })}
            </nav>

            <div className="p-4 border-t">
                {!collapsed && (
                    <div className="rounded-md bg-muted p-4">
                        <div className="flex items-center gap-3">
                            <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center">
                                <span className="text-xs font-bold text-primary">AD</span>
                            </div>
                            <div className="flex flex-col overflow-hidden">
                                <span className="text-sm font-medium truncate">Admin User</span>
                                <span className="text-xs text-muted-foreground truncate">admin@example.com</span>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
