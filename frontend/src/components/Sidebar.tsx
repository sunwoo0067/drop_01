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

const quickLinks = [
    { name: "가공", href: "/processing", icon: Wand2 },
    { name: "등록", href: "/registration", icon: Upload },
    { name: "소싱", href: "/sourcing", icon: Search },
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
            "flex flex-col border-r bg-card h-screen transition-all duration-300 ease-in-out relative z-30",
            collapsed ? "w-16" : "w-64"
        )}>
            {/* Collapse Toggle Button - Improved positioning and design */}
            <button
                onClick={() => setCollapsed(!collapsed)}
                aria-label={collapsed ? "사이드바 펼치기" : "사이드바 접기"}
                className="absolute -right-3 top-6 flex h-6 w-6 items-center justify-center rounded-full bg-background border border-border shadow-md hover:bg-muted transition-all active:scale-95 z-40"
            >
                {collapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronLeft className="h-3 w-3" />}
            </button>

            {/* Logo Section - Professional branding */}
            <div className="flex h-16 items-center px-5 border-b border-border/50">
                <Link href="/" className="flex items-center gap-3 group">
                    <div className="h-9 w-9 rounded-xl bg-primary flex items-center justify-center shrink-0 shadow-lg shadow-primary/20 group-hover:scale-105 transition-transform">
                        <Package className="h-5 w-5 text-primary-foreground" />
                    </div>
                    {!collapsed && (
                        <div className="flex flex-col">
                            <span className="text-sm font-black text-foreground tracking-tighter uppercase italic leading-none">
                                DROP AUTOMATA
                            </span>
                            <span className="text-[9px] text-muted-foreground font-bold tracking-[0.2em] uppercase mt-1 opacity-70">
                                AI ERP SYSTEM
                            </span>
                        </div>
                    )}
                </Link>
            </div>

            {/* Quick Actions - Simplified and more visible */}
            {!collapsed && (
                <div className="px-4 py-4 border-b border-border/40">
                    <div className="grid grid-cols-3 gap-2">
                        {quickLinks.map((item) => (
                            <Link
                                key={item.href}
                                href={item.href}
                                className="flex flex-col items-center gap-1.5 rounded-xl border border-border/50 bg-accent/30 p-2 text-[10px] font-bold text-foreground hover:bg-accent hover:border-primary/30 transition-all hover:-translate-y-0.5"
                                title={item.name}
                            >
                                <item.icon className="h-3.5 w-3.5 text-primary" />
                                <span className="opacity-80">{item.name}</span>
                            </Link>
                        ))}
                    </div>
                </div>
            )}

            {/* Navigation Section - Better grouping and visual hierarchy */}
            <nav className="flex-1 overflow-y-auto overflow-x-hidden py-4 px-3 space-y-6 scrollbar-hide">
                {menuGroups.map((group) => (
                    <div key={group.title} className="space-y-1">
                        {!collapsed && (
                            <div className="px-2 mb-2 flex items-center justify-between">
                                <span className="text-[10px] font-black text-muted-foreground/50 uppercase tracking-[0.15em]">
                                    {group.title}
                                </span>
                            </div>
                        )}
                        <div className="space-y-0.5">
                            {group.items.map((item) => {
                                const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));
                                return (
                                    <Link
                                        key={item.href}
                                        href={item.href}
                                        className={cn(
                                            "flex items-center px-3 py-2.5 text-xs font-bold transition-all rounded-xl relative group",
                                            isActive
                                                ? "bg-primary/10 text-primary shadow-sm shadow-primary/5"
                                                : "text-muted-foreground/80 hover:bg-accent hover:text-foreground",
                                            collapsed && "justify-center px-0 h-10 w-10 mx-auto"
                                        )}
                                        title={collapsed ? item.name : ""}
                                    >
                                        <item.icon
                                            className={cn(
                                                "h-4 w-4 transition-transform group-hover:scale-110",
                                                !collapsed && "mr-3",
                                                isActive ? "text-primary" : "opacity-70 group-hover:opacity-100"
                                            )}
                                        />
                                        {!collapsed && <span>{item.name}</span>}

                                        {isActive && !collapsed && (
                                            <div className="absolute left-0 w-1 h-4 bg-primary rounded-full my-auto" />
                                        )}
                                    </Link>
                                );
                            })}
                        </div>
                    </div>
                ))}
            </nav>

            {/* User Profile Section - Clean and modern */}
            <div className="p-4 border-t border-border/50">
                <div className={cn(
                    "flex items-center p-2 rounded-2xl border border-border/50 bg-accent/20",
                    collapsed ? "justify-center h-12 w-12 mx-auto" : "gap-3"
                )}>
                    <div className="h-8 w-8 rounded-full bg-gradient-to-br from-primary/20 to-primary/40 flex items-center justify-center shrink-0 border border-primary/20 shadow-inner">
                        <User className="h-4 w-4 text-primary" />
                    </div>
                    {!collapsed && (
                        <div className="flex flex-col min-w-0 flex-1">
                            <span className="text-[12px] font-black text-foreground truncate leading-none">Admin User</span>
                            <div className="flex items-center gap-1 mt-1">
                                <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                                <span className="text-[9px] text-muted-foreground font-bold uppercase tracking-wider">Premium</span>
                            </div>
                        </div>
                    )}
                    {!collapsed && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-xl"
                        >
                            <LogOut className="h-3.5 w-3.5" />
                        </Button>
                    )}
                </div>
            </div>
        </div>
    );
}
