"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
    LayoutDashboard,
    Package,
    Search,
    Settings,
    Bot,
    ChevronLeft,
    ChevronRight,
    ShoppingBag
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

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
            "flex flex-col border-r bg-card h-screen transition-all duration-300 ease-in-out relative",
            collapsed ? "w-16" : "w-64"
        )}>
            {/* Collapse Toggle Button */}
            <button
                onClick={() => setCollapsed(!collapsed)}
                aria-label={collapsed ? "사이드바 펼치기" : "사이드바 접기"}
                className="absolute -right-3 top-20 flex h-6 w-6 items-center justify-center rounded-full border bg-background shadow-sm hover:bg-accent transition-colors z-10"
            >
                {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
            </button>

            {/* Logo Section */}
            <div className="flex h-16 items-center border-b px-6">
                <div className="flex items-center gap-3">
                    <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center shrink-0">
                        <Package className="h-5 w-5 text-primary-foreground" />
                    </div>
                    {!collapsed && (
                        <span className="text-xl font-bold bg-gradient-to-r from-primary to-blue-400 bg-clip-text text-transparent transition-all">
                            DropAutomata
                        </span>
                    )}
                </div>
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
