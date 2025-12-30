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
    Database,
    Upload,
    Store,
    TrendingUp,
    ChevronDown
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";

const menuGroups = [
    {
        title: "개요",
        items: [
            { name: "대시보드", href: "/", icon: LayoutDashboard },
        ]
    },
    {
        title: "시장 관리",
        items: [
            { name: "상품 관리", href: "/products", icon: Package },
            { name: "상품 가공", href: "/processing", icon: Wand2 },
            { name: "상품 등록", href: "/registration", icon: Upload },
            { name: "마켓 상품", href: "/market-products", icon: Store },
            { name: "주문 동기화", href: "/order-sync", icon: ShoppingBag },
            { name: "상품 소싱", href: "/sourcing", icon: Search },
            { name: "벤치마크", href: "/benchmarks", icon: BarChart3 },
        ]
    },
    {
        title: "데이터 수집",
        items: [
            { name: "공급사 상품수집", href: "/suppliers", icon: Download },
            { name: "공급사 상품목록", href: "/suppliers/items", icon: Database },
        ]
    },
    {
        title: "인텔리전스",
        items: [
            { name: "에이전트", href: "/agents", icon: Bot },
            { name: "매출 분석", href: "/analytics", icon: TrendingUp },
        ]
    },
    {
        title: "시스템",
        items: [
            { name: "설정", href: "/settings", icon: Settings },
        ]
    }
];


export default function Sidebar() {
    const pathname = usePathname();
    const [collapsed, setCollapsed] = useState(false);
    const [expandedGroups, setExpandedGroups] = useState<string[]>(
        menuGroups.map(g => g.title)
    );

    const toggleGroup = (title: string) => {
        setExpandedGroups(prev =>
            prev.includes(title)
                ? prev.filter(t => t !== title)
                : [...prev, title]
        );
    };

    return (
        <div className={cn(
            "flex flex-col border-r bg-card h-screen",
            collapsed ? "w-16" : "w-56"
        )}>
            {/* Collapse Toggle Button */}
            <button
                onClick={() => setCollapsed(!collapsed)}
                aria-label={collapsed ? "사이드바 펼치기" : "사이드바 접기"}
                className="absolute -right-3 top-4 flex h-5 w-5 items-center justify-center rounded bg-background border border-border shadow-sm hover:bg-muted transition-colors z-10"
            >
                {collapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronLeft className="h-3 w-3" />}
            </button>

            {/* Logo Section */}
            <div className="flex h-12 items-center px-4 border-b border-border">
                <div className="flex items-center gap-2">
                    <div className="h-8 w-8 rounded-sm bg-primary flex items-center justify-center shrink-0">
                        <Package className="h-4 w-4 text-primary-foreground" />
                    </div>
                    {!collapsed && (
                        <div className="flex flex-col">
                            <span className="text-sm font-bold text-foreground tracking-tight">
                                DROP AUTOMATA
                            </span>
                            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
                                ERP System
                            </span>
                        </div>
                    )}
                </div>
            </div>

            {/* Navigation Section */}
            <nav className="flex-1 overflow-y-auto overflow-x-hidden py-2 table-scroll">
                {menuGroups.map((group) => (
                    <div key={group.title} className="border-b border-border/50">
                        {!collapsed && (
                            <button
                                onClick={() => toggleGroup(group.title)}
                                className="w-full px-4 py-2 flex items-center justify-between hover:bg-muted transition-colors"
                            >
                                <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                                    {group.title}
                                </span>
                                <ChevronDown
                                    className={cn(
                                        "h-3 w-3 text-muted-foreground transition-transform",
                                        expandedGroups.includes(group.title) ? "rotate-180" : ""
                                    )}
                                />
                            </button>
                        )}
                        {(collapsed || expandedGroups.includes(group.title)) && (
                            <div className="space-y-0.5">
                                {group.items.map((item) => {
                                    const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));
                                    return (
                                        <Link
                                            key={item.href}
                                            href={item.href}
                                            className={cn(
                                                "flex items-center px-4 py-2 text-xs font-medium transition-colors border-l-2",
                                                isActive
                                                    ? "bg-primary/10 text-primary border-primary"
                                                    : "text-muted-foreground border-transparent hover:bg-muted hover:text-foreground",
                                                collapsed && "justify-center px-0 h-8 w-8 mx-auto"
                                            )}
                                            title={collapsed ? item.name : ""}
                                        >
                                            <item.icon
                                                className={cn(
                                                    "h-4 w-4 flex-shrink-0",
                                                    !collapsed && "mr-2"
                                                )}
                                            />
                                            {!collapsed && <span>{item.name}</span>}
                                        </Link>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                ))}
            </nav>

            {/* User Profile Section */}
            <div className="p-3 border-t border-border">
                <div className={cn(
                    "w-full border border-border",
                    !collapsed && "p-2"
                )}>
                    <div className={cn(
                        "flex items-center",
                        collapsed ? "justify-center" : "gap-2"
                    )}>
                        <div className="h-7 w-7 rounded-sm bg-secondary flex items-center justify-center shrink-0 border border-border">
                            <User className="h-4 w-4 text-foreground" />
                        </div>
                        {!collapsed && (
                            <div className="flex flex-col min-w-0 flex-1">
                                <span className="text-xs font-semibold truncate">Admin User</span>
                                <span className="text-[10px] text-muted-foreground truncate uppercase">License: Premium</span>
                            </div>
                        )}
                        {!collapsed && (
                            <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-sm">
                                <LogOut className="h-3 w-3" />
                            </Button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
