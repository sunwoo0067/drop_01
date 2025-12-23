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
    Store
} from "lucide-react";
import { useState } from "react";
import { motion } from "framer-motion";
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
            { name: "상품 등록", href: "/registration", icon: Upload },
            { name: "마켓 상품", href: "/market-products", icon: Store },
            { name: "주문 동기화", href: "/order-sync", icon: ShoppingBag },
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
            <div className="flex h-20 items-center px-6 mb-2">
                <div className="flex items-center gap-3">
                    <motion.div
                        whileHover={{ rotate: 10, scale: 1.1 }}
                        className="h-10 w-10 rounded-xl bg-gradient-to-br from-primary to-blue-600 flex items-center justify-center shrink-0 shadow-lg shadow-primary/20"
                    >
                        <Package className="h-6 w-6 text-primary-foreground" />
                    </motion.div>
                    {!collapsed && (
                        <div className="flex flex-col">
                            <span className="text-lg font-black tracking-tighter bg-gradient-to-r from-primary via-blue-500 to-indigo-400 bg-clip-text text-transparent transition-all">
                                DROP AUTOMATA
                            </span>
                            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest leading-none">
                                AI Management
                            </span>
                        </div>
                    )}
                </div>
            </div>

            {/* Navigation Section */}
            <nav className="flex-1 overflow-y-auto overflow-x-hidden py-4 px-3 space-y-8 custom-scrollbar">
                {menuGroups.map((group) => (
                    <div key={group.title} className="relative">
                        {!collapsed && (
                            <h2 className="px-4 text-[10px] font-extrabold text-muted-foreground/60 uppercase tracking-[0.2em] mb-3">
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
                                            "group relative flex items-center rounded-xl px-4 py-3 text-sm font-semibold transition-all duration-300",
                                            isActive
                                                ? "bg-primary text-primary-foreground shadow-md shadow-primary/20"
                                                : "text-muted-foreground hover:bg-accent/80 hover:text-foreground",
                                            collapsed && "justify-center px-0 h-12 w-12 mx-auto"
                                        )}
                                        title={collapsed ? item.name : ""}
                                    >
                                        <item.icon
                                            className={cn(
                                                "h-5 w-5 flex-shrink-0 transition-all duration-300",
                                                isActive ? "text-primary-foreground" : "text-muted-foreground group-hover:text-foreground group-hover:scale-110",
                                                !collapsed && "mr-3"
                                            )}
                                        />
                                        {!collapsed && <span>{item.name}</span>}

                                        {/* Active Indicator Bar */}
                                        {isActive && !collapsed && (
                                            <motion.div
                                                layoutId="active-nav-indicator"
                                                className="absolute left-1 h-5 w-1 bg-primary-foreground rounded-full"
                                            />
                                        )}
                                    </Link>
                                );
                            })}
                        </div>
                    </div>
                ))}
            </nav>

            {/* User Profile Section */}
            <div className="p-4 border-t border-glass-border">
                <div className={cn(
                    "w-full rounded-2xl transition-all duration-300",
                    !collapsed && "bg-gradient-to-br from-accent/40 to-accent/10 p-4 border border-glass-border hover:shadow-lg"
                )}>
                    <div className={cn(
                        "flex items-center",
                        collapsed ? "justify-center" : "gap-3"
                    )}>
                        <div className="h-10 w-10 rounded-full bg-gradient-to-tr from-primary/20 to-blue-500/10 flex items-center justify-center shrink-0 border border-primary/20 shadow-inner">
                            <User className="h-6 w-6 text-primary" />
                        </div>
                        {!collapsed && (
                            <div className="flex flex-col min-w-0">
                                <span className="text-sm font-bold truncate leading-none mb-1">Admin User</span>
                                <span className="text-[10px] text-muted-foreground truncate uppercase font-medium tracking-tighter">Premium License</span>
                            </div>
                        )}
                        {!collapsed && (
                            <Button variant="ghost" size="icon" className="ml-auto h-8 w-8 text-muted-foreground/60 hover:text-destructive hover:bg-destructive/10 transition-all duration-300 rounded-lg">
                                <LogOut className="h-4 w-4" />
                            </Button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
