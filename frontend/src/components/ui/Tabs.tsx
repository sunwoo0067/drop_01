"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

interface TabsContextProps {
    value: string;
    onValueChange: (value: string) => void;
}

const TabsContext = createContext<TabsContextProps | undefined>(undefined);

export function Tabs({
    value,
    onValueChange,
    defaultValue,
    children,
    className
}: {
    value?: string;
    onValueChange?: (value: string) => void;
    defaultValue?: string;
    children: React.ReactNode;
    className?: string;
}) {
    const [internalValue, setInternalValue] = useState(defaultValue || "");

    const activeValue = value !== undefined ? value : internalValue;
    const handleValueChange = (val: string) => {
        if (value === undefined) setInternalValue(val);
        onValueChange?.(val);
    };

    return (
        <TabsContext.Provider value={{ value: activeValue, onValueChange: handleValueChange }}>
            <div className={cn("w-full", className)}>
                {children}
            </div>
        </TabsContext.Provider>
    );
}

export function TabsList({ children, className }: { children: React.ReactNode, className?: string }) {
    return (
        <div className={cn("flex space-x-1 bg-muted/30 p-1 rounded-xl border border-border/50 backdrop-blur-md", className)}>
            {children}
        </div>
    );
}

export function TabsTrigger({
    value,
    label,
    icon,
    count,
    className
}: {
    value: string,
    label?: string,
    icon?: React.ReactNode,
    count?: number,
    className?: string
}) {
    const context = useContext(TabsContext);
    if (!context) throw new Error("TabsTrigger must be used within Tabs");

    const isActive = context.value === value;

    return (
        <button
            onClick={() => context.onValueChange(value)}
            className={cn(
                "relative px-5 py-2.5 text-sm font-medium transition-all focus-visible:outline-none rounded-lg flex items-center justify-center gap-2 flex-1",
                isActive ? "text-primary-foreground" : "text-muted-foreground hover:text-foreground hover:bg-muted/50",
                className
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
                {icon && <span className="h-4 w-4">{icon}</span>}
                {label || value}
                {count !== undefined && (
                    <span className={cn(
                        "px-1.5 py-0.5 text-[11px] font-bold rounded-md min-w-[1.25rem] text-center",
                        isActive ? "bg-white/20 text-white" : "bg-muted text-muted-foreground"
                    )}>
                        {count.toLocaleString()}
                    </span>
                )}
            </span>
        </button>
    );
}

export function TabsContent({ value, children, className }: { value: string, children: React.ReactNode, className?: string }) {
    const context = useContext(TabsContext);
    if (!context) throw new Error("TabsContent must be used within Tabs");

    return (
        <AnimatePresence mode="wait">
            {context.value === value && (
                <motion.div
                    key={value}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.2 }}
                    className={cn("focus-visible:outline-none", className)}
                >
                    {children}
                </motion.div>
            )}
        </AnimatePresence>
    );
}
