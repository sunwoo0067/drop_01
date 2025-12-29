"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { Search, Package, LayoutDashboard, Settings, Wand2, Upload, Store, ShoppingBag, Bot, TrendingUp, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface CommandItem {
    name: string;
    href: string;
    icon: any;
    category: string;
}

const commands: CommandItem[] = [
    { name: "대시보드", href: "/", icon: LayoutDashboard, category: "일반" },
    { name: "상품 관리", href: "/products", icon: Package, category: "시장 관리" },
    { name: "상품 가공", href: "/processing", icon: Wand2, category: "시장 관리" },
    { name: "상품 등록", href: "/registration", icon: Upload, category: "시장 관리" },
    { name: "마켓 상품", href: "/market-products", icon: Store, category: "시장 관리" },
    { name: "주문 동기화", href: "/order-sync", icon: ShoppingBag, category: "시장 관리" },
    { name: "에이전트", href: "/agents", icon: Bot, category: "인텔리전스" },
    { name: "매출 분석", href: "/analytics", icon: TrendingUp, category: "인텔리전스" },
    { name: "설정", href: "/settings", icon: Settings, category: "시스템" },
];

export default function CommandPalette() {
    const [isOpen, setIsOpen] = useState(false);
    const [search, setSearch] = useState("");
    const [selectedIndex, setSelectedIndex] = useState(0);
    const router = useRouter();
    const inputRef = useRef<HTMLInputElement>(null);

    const filteredCommands = commands.filter(cmd =>
        cmd.name.toLowerCase().includes(search.toLowerCase()) ||
        cmd.category.toLowerCase().includes(search.toLowerCase())
    );

    const toggleOpen = useCallback(() => {
        setIsOpen(prev => !prev);
        setSearch("");
        setSelectedIndex(0);
    }, []);

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                toggleOpen();
            }
            if (e.key === "Escape") {
                setIsOpen(false);
            }
        };

        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, [toggleOpen]);

    useEffect(() => {
        if (isOpen && inputRef.current) {
            inputRef.current.focus();
        }
    }, [isOpen]);

    const handleSelect = (href: string) => {
        router.push(href);
        setIsOpen(false);
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "ArrowDown") {
            e.preventDefault();
            setSelectedIndex(prev => (prev + 1) % filteredCommands.length);
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setSelectedIndex(prev => (prev - 1 + filteredCommands.length) % filteredCommands.length);
        } else if (e.key === "Enter") {
            if (filteredCommands[selectedIndex]) {
                handleSelect(filteredCommands[selectedIndex].href);
            }
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[10vh] bg-background/40 backdrop-blur-sm px-4">
            <div className="w-full max-w-lg bg-card border border-border rounded-xl shadow-2xl overflow-hidden animate-in fade-in slide-in-from-top-4 duration-200">
                <div className="flex items-center px-4 py-3 border-b border-border gap-3">
                    <Search className="h-5 w-5 text-muted-foreground" />
                    <input
                        ref={inputRef}
                        type="text"
                        placeholder="전체 메뉴 및 기능 검색 (Ctrl + K)"
                        className="flex-1 bg-transparent border-none outline-none text-sm font-medium placeholder:text-muted-foreground"
                        value={search}
                        onChange={(e) => {
                            setSearch(e.target.value);
                            setSelectedIndex(0);
                        }}
                        onKeyDown={handleKeyDown}
                    />
                    <button
                        onClick={() => setIsOpen(false)}
                        className="p-1 rounded-sm hover:bg-muted text-muted-foreground transition-colors"
                    >
                        <X className="h-4 w-4" />
                    </button>
                </div>

                <div className="max-h-[300px] overflow-y-auto p-2 table-scroll">
                    {filteredCommands.length > 0 ? (
                        <div className="space-y-1">
                            {filteredCommands.map((cmd, idx) => (
                                <button
                                    key={cmd.href}
                                    onClick={() => handleSelect(cmd.href)}
                                    className={cn(
                                        "w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-all group",
                                        idx === selectedIndex ? "bg-primary text-primary-foreground" : "hover:bg-muted text-foreground"
                                    )}
                                >
                                    <div className="flex items-center gap-3">
                                        <cmd.icon className={cn(
                                            "h-4 w-4",
                                            idx === selectedIndex ? "text-primary-foreground" : "text-muted-foreground group-hover:text-foreground"
                                        )} />
                                        <span className="font-semibold">{cmd.name}</span>
                                    </div>
                                    <span className={cn(
                                        "text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded",
                                        idx === selectedIndex ? "bg-primary-foreground/20 text-primary-foreground" : "bg-muted text-muted-foreground"
                                    )}>
                                        {cmd.category}
                                    </span>
                                </button>
                            ))}
                        </div>
                    ) : (
                        <div className="py-12 text-center text-muted-foreground">
                            <Search className="h-8 w-8 mx-auto mb-3 opacity-20" />
                            <p className="text-xs font-medium">검색 결과가 없습니다.</p>
                        </div>
                    )}
                </div>

                <div className="px-4 py-2 border-t border-border bg-muted/30 flex items-center justify-between text-[10px] text-muted-foreground font-bold uppercase tracking-wider">
                    <div className="flex gap-4">
                        <span className="flex items-center gap-1"><kbd className="border border-border bg-background px-1 rounded shadow-sm">Enter</kbd> 선택</span>
                        <span className="flex items-center gap-1"><kbd className="border border-border bg-background px-1 rounded shadow-sm">↑↓</kbd> 이동</span>
                    </div>
                    <span>ESC 닫기</span>
                </div>
            </div>
            <div className="fixed inset-0 -z-10" onClick={() => setIsOpen(false)} />
        </div>
    );
}
