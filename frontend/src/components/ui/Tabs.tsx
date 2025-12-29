"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

interface Tab {
    id: string;
    label: string;
    count?: number;
}

interface TabsProps {
    tabs: Tab[];
    activeTab: string;
    onChange: (id: string) => void;
    className?: string;
}

export function Tabs({ tabs, activeTab, onChange, className }: TabsProps) {
    return (
        <div className={cn("flex space-x-1 bg-muted/30 p-1 rounded-xl border border-border/50 backdrop-blur-md", className)}>
            {tabs.map((tab) => {
                const isActive = activeTab === tab.id;
                return (
                    <button
                        key={tab.id}
                        onClick={() => onChange(tab.id)}
                        className={cn(
                            "relative px-5 py-2.5 text-sm font-medium transition-all focus-visible:outline-none rounded-lg",
                            isActive ? "text-primary-foreground" : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                        )}
                    >
                        {isActive && (
                            <motion.div
                                layoutId="active-tab"
                                className="absolute inset-0 bg-primary shadow-sm rounded-lg"
                                transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                            />
                        )}
                        <span className="relative z-10 flex items-center gap-2">
                            {tab.label}
                            {tab.count !== undefined && (
                                <span className={cn(
                                    "px-1.5 py-0.5 text-[11px] font-bold rounded-md min-w-[1.25rem] text-center",
                                    isActive ? "bg-white/20 text-white" : "bg-muted text-muted-foreground"
                                )}>
                                    {tab.count.toLocaleString()}
                                </span>
                            )}
                        </span>
                    </button>
                );
            })}
        </div>
    );
}

interface TabsContentProps {
    value: string;
    activeTab: string;
    children: React.ReactNode;
}

export function TabsContent({ value, activeTab, children }: TabsContentProps) {
    return (
        <AnimatePresence mode="wait">
            {value === activeTab && (
                <motion.div
                    key={value}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.2 }}
                >
                    {children}
                </motion.div>
            )}
        </AnimatePresence>
    );
}
