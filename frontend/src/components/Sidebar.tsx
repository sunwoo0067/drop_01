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
    LogOut,
    User,
    ShoppingBag,
    Wand2,
    BarChart3,
    Download,
    Database
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";

const menuGroups = [
    {
        title: "Overview",
        items: [
            { name: "대시보드", href: "/", icon: LayoutDashboard },
        ]
    },
    {
        title: "Market Management",
        items: [
            { name: "상품 관리", href: "/products", icon: Package },
            { name: "상품 가공", href: "/processing", icon: Wand2 },
            { name: "상품 소싱", href: "/sourcing", icon: Search },
            { name: "벤치마크", href: "/benchmarks", icon: BarChart3 },
        ]
    },
    {
        title: "Data Collection",
        items: [
            { name: "공급사 상품수집", href: "/suppliers", icon: Download },
            { name: "공급사 상품목록", href: "/suppliers/items", icon: Database },
        ]
    },
    {
        title: "Intelligence",
        items: [
            { name: "에이전트", href: "/agents", icon: Bot },
        ]
    },
    {
        title: "System",
        items: [
            { name: "설정", href: "/settings", icon: Settings },
        ]
    }
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

            {/* Navigation Section */}
            <nav className="flex-1 overflow-y-auto overflow-x-hidden py-4 px-3 custom-scrollbar">
                {menuGroups.map((group, groupIdx) => (
                    <div key={group.title} className={cn("mb-6", groupIdx === 0 && "mt-0")}>
                        {!collapsed && (
                            <h2 className="px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                                {group.title}
                            </h2>
                        )}
                        <div className="space-y-1">
                            {group.items.map((item) => {
                                const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));
                                return (
                                    <Link
                                        key={item.href}
                                        href={item.href}
                                        className={cn(
                                            "group relative flex items-center rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200",
                                            isActive
                                                ? "bg-primary/10 text-primary"
                                                : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                                            collapsed && "justify-center"
                                        )}
                                        title={collapsed ? item.name : ""}
                                    >
                                        <item.icon
                                            className={cn(
                                                "h-5 w-5 flex-shrink-0 transition-transform duration-200 group-hover:scale-110",
                                                isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
                                                !collapsed && "mr-3"
                                            )}
                                        />
                                        {!collapsed && <span>{item.name}</span>}

                                        {/* Active Indicator */}
                                        {isActive && !collapsed && (
                                            <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-primary rounded-r-full" />
                                        )}
                                    </Link>
                                );
                            })}
                        </div>
                    </div>
                ))}
            </nav>

            {/* User Profile Section */}
            <div className="p-4 border-t h-[90px] flex items-center">
                <div className={cn(
                    "w-full rounded-xl transition-all duration-200",
                    !collapsed && "bg-accent/30 p-3 hover:bg-accent/50"
                )}>
                    <div className={cn(
                        "flex items-center",
                        collapsed ? "justify-center" : "gap-3"
                    )}>
                        <div className="h-9 w-9 rounded-full bg-primary/20 flex items-center justify-center shrink-0 border border-primary/10">
                            <User className="h-5 w-5 text-primary" />
                        </div>
                        {!collapsed && (
                            <div className="flex flex-col min-w-0">
                                <span className="text-sm font-semibold truncate leading-none mb-1">Admin User</span>
                                <span className="text-xs text-muted-foreground truncate">admin@drop.ai</span>
                            </div>
                        )}
                        {!collapsed && (
                            <Button variant="ghost" size="icon" className="ml-auto h-8 w-8 text-muted-foreground hover:text-destructive transition-colors">
                                <LogOut className="h-4 w-4" />
                            </Button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
