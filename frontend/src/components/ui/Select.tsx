"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { ChevronDown, Check } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

// --- Context ---
interface SelectContextValue {
    value?: string;
    onValueChange?: (value: string) => void;
    open: boolean;
    setOpen: (open: boolean) => void;
    selectedLabel: React.ReactNode;
    setSelectedLabel: (label: React.ReactNode) => void;
}

const SelectContext = React.createContext<SelectContextValue | null>(null);

// --- Native Select (Legacy Compatibility) ---
const NativeSelect = React.forwardRef<HTMLSelectElement, any>(
    ({ className, label, error, options, ...props }, ref) => {
        return (
            <div className="w-full">
                {label && (
                    <label className="block text-sm font-medium mb-1.5 text-foreground/90">
                        {label}
                    </label>
                )}
                <div className="relative">
                    <select
                        className={cn(
                            "flex h-10 w-full items-center justify-between rounded-xl border border-glass-border bg-background/50 backdrop-blur-md px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50 appearance-none transition-all duration-200",
                            error && "border-destructive focus:ring-destructive",
                            className
                        )}
                        ref={ref}
                        {...props}
                    >
                        {options?.map((opt: any) => (
                            <option key={opt.value} value={opt.value}>
                                {opt.label}
                            </option>
                        ))}
                    </select>
                    <div className="absolute right-3 top-2.5 pointer-events-none text-muted-foreground">
                        <ChevronDown className="h-4 w-4" />
                    </div>
                </div>
                {error && <p className="text-xs text-destructive mt-1 font-medium">{error}</p>}
            </div>
        );
    }
);
NativeSelect.displayName = "NativeSelect";

// --- Modular Select Components ---

const Select = React.forwardRef<any, any>(({ children, value, onValueChange, ...props }, ref) => {
    // If options prop is present, use legacy NativeSelect
    if (props.options) {
        return <NativeSelect ref={ref} value={value} onChange={(e: any) => onValueChange?.(e.target.value)} {...props} />;
    }

    const [open, setOpen] = React.useState(false);
    const [selectedLabel, setSelectedLabel] = React.useState<React.ReactNode>(null);
    const containerRef = React.useRef<HTMLDivElement>(null);

    // Close on outside click
    React.useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
                setOpen(false);
            }
        };
        if (open) {
            document.addEventListener("mousedown", handleClickOutside);
        }
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, [open]);

    return (
        <SelectContext.Provider value={{ value, onValueChange, open, setOpen, selectedLabel, setSelectedLabel }}>
            <div className="relative w-full" ref={containerRef}>
                {children}
            </div>
        </SelectContext.Provider>
    );
});
Select.displayName = "Select";

const SelectTrigger = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement>>(
    ({ className, children, ...props }, ref) => {
        const context = React.useContext(SelectContext);
        if (!context) return null;

        return (
            <button
                ref={ref}
                type="button"
                onClick={() => context.setOpen(!context.open)}
                className={cn(
                    "flex h-10 w-full items-center justify-between rounded-xl border border-glass-border bg-background/50 backdrop-blur-md px-4 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50 transition-all duration-200 hover:border-primary/30",
                    className
                )}
                {...props}
            >
                {children}
                <motion.div
                    animate={{ rotate: context.open ? 180 : 0 }}
                    transition={{ duration: 0.2 }}
                >
                    <ChevronDown className="h-4 w-4 opacity-50" />
                </motion.div>
            </button>
        );
    }
);
SelectTrigger.displayName = "SelectTrigger";

const SelectValue = ({ placeholder, className }: { placeholder?: string; className?: string }) => {
    const context = React.useContext(SelectContext);
    if (!context) return null;

    return (
        <span className={cn("truncate text-foreground/90", className)}>
            {context.selectedLabel || placeholder}
        </span>
    );
};

const SelectContent = ({ children, className }: { children: React.ReactNode; className?: string }) => {
    const context = React.useContext(SelectContext);
    if (!context) return null;

    return (
        <AnimatePresence>
            {context.open && (
                <motion.div
                    initial={{ opacity: 0, y: -10, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -10, scale: 0.95 }}
                    transition={{ duration: 0.1, ease: "easeOut" }}
                    className={cn(
                        "absolute z-50 mt-2 max-h-60 w-full overflow-auto rounded-2xl border border-glass-border bg-card/90 backdrop-blur-xl p-1.5 text-card-foreground shadow-2xl ring-1 ring-black/5",
                        className
                    )}
                >
                    {children}
                </motion.div>
            )}
        </AnimatePresence>
    );
};

const SelectItem = ({ value, children, className }: { value: string; children: React.ReactNode; className?: string }) => {
    const context = React.useContext(SelectContext);
    if (!context) return null;

    const isSelected = context.value === value;

    // Track the label of the selected value
    React.useEffect(() => {
        if (isSelected) {
            context.setSelectedLabel(children);
        }
    }, [isSelected, children, context]);

    return (
        <div
            onClick={() => {
                context.onValueChange?.(value);
                context.setOpen(false);
            }}
            className={cn(
                "relative flex w-full cursor-pointer select-none items-center rounded-lg py-2.5 pl-10 pr-4 text-sm outline-none transition-colors",
                "hover:bg-primary/5 hover:text-primary",
                isSelected ? "bg-primary/10 text-primary font-medium" : "text-foreground/80",
                className
            )}
        >
            <span className="absolute left-3 flex h-3.5 w-3.5 items-center justify-center">
                {isSelected && (
                    <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }}>
                        <Check className="h-4 w-4" />
                    </motion.div>
                )}
            </span>
            {children}
        </div>
    );
};

export { Select, SelectTrigger, SelectValue, SelectContent, SelectItem };
