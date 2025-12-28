"use client";

import React, { useState } from "react";
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
        <div className={cn("flex space-x-1 bg-slate-900/50 p-1 rounded-xl backdrop-blur-sm border border-slate-800", className)}>
            {tabs.map((tab) => {
                const isActive = activeTab === tab.id;
                return (
                    <button
                        key={tab.id}
                        onClick={() => onChange(tab.id)}
                        className={cn(
                            "relative px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none",
                            isActive ? "text-white" : "text-slate-400 hover:text-slate-200"
                        )}
                    >
                        {isActive && (
                            <motion.div
                                layoutId="active-tab"
                                className="absolute inset-0 bg-slate-800 rounded-lg shadow-lg"
                                transition={{ type: "spring", duration: 0.5 }}
                            />
                        )}
                        <span className="relative z-10 flex items-center">
                            {tab.label}
                            {tab.count !== undefined && (
                                <span className={cn(
                                    "ml-2 px-1.5 py-0.5 text-[10px] rounded-full",
                                    isActive ? "bg-blue-500 text-white" : "bg-slate-700 text-slate-300"
                                )}>
                                    {tab.count}
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
