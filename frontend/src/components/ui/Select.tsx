"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { ChevronDown } from "lucide-react";

const NativeSelect = React.forwardRef<HTMLSelectElement, any>(
    ({ className, error, options, size = "md", ...props }, ref) => {
        const sizes = {
            xs: "h-6 text-[10px] px-2",
            sm: "h-7 text-xs px-2",
            md: "h-8 text-sm px-2.5",
        };

        return (
            <div className="w-full">
                <div className="relative">
                    <select
                        className={cn(
                            "flex w-full items-center justify-between rounded-sm border border-border bg-background appearance-none",
                            "focus:outline-none focus:ring-1 focus:ring-primary",
                            "disabled:cursor-not-allowed disabled:opacity-50",
                            "transition-colors",
                            sizes[size as keyof typeof sizes],
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
                    <div className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground">
                        <ChevronDown className="h-3 w-3" />
                    </div>
                </div>
            </div>
        );
    }
);
NativeSelect.displayName = "NativeSelect";

const SelectContext = React.createContext<any>(null);

interface SelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "size"> {
    onValueChange?: (value: string) => void;
    options?: { value: string; label: string }[];
    error?: boolean;
    size?: "xs" | "sm" | "md";
    label?: string;
}

const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
    ({ children, value, onValueChange, ...props }, ref) => {
        // If options prop is present, use legacy NativeSelect
        if (props.options) {
            return (
                <NativeSelect
                    ref={ref}
                    value={value}
                    onChange={(e: any) => {
                        props.onChange?.(e);
                        onValueChange?.(e.target.value);
                    }}
                    {...props}
                />
            );
        }

        return (
            <SelectContext.Provider value={{ value, onValueChange }}>
                <div className="relative w-full">{children}</div>
            </SelectContext.Provider>
        );
    }
);
Select.displayName = "Select";

const SelectTrigger = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
    ({ className, children, ...props }, ref) => (
        <div
            ref={ref}
            className={cn(
                "flex h-8 w-full items-center justify-between rounded-sm border border-border bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-50",
                className
            )}
            {...props}
        >
            {children}
            <ChevronDown className="h-4 w-4 opacity-50" />
        </div>
    )
);
SelectTrigger.displayName = "SelectTrigger";

const SelectValue = React.forwardRef<HTMLSpanElement, React.HTMLAttributes<HTMLSpanElement> & { placeholder?: string }>(
    ({ className, placeholder, ...props }, ref) => {
        const { value } = React.useContext(SelectContext);
        return (
            <span ref={ref} className={cn("block truncate text-sm", className)} {...props}>
                {value || placeholder}
            </span>
        );
    }
);
SelectValue.displayName = "SelectValue";

const SelectContent = ({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
    <div
        className={cn(
            "absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-sm border border-border bg-popover text-popover-foreground shadow-md animate-in fade-in zoom-in-95",
            className
        )}
        {...props}
    >
        <div className="p-1">{children}</div>
    </div>
);

const SelectItem = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement> & { value: string }>(
    ({ className, children, value, ...props }, ref) => {
        const { onValueChange, value: selectedValue } = React.useContext(SelectContext);
        const isSelected = selectedValue === value;

        return (
            <div
                ref={ref}
                className={cn(
                    "relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none hover:bg-accent hover:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
                    isSelected && "bg-accent text-accent-foreground",
                    className
                )}
                onClick={() => onValueChange?.(value)}
                {...props}
            >
                <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                    {isSelected && <div className="h-2 w-2 rounded-full bg-primary" />}
                </span>
                {children}
            </div>
        );
    }
);
SelectItem.displayName = "SelectItem";

export { Select, SelectTrigger, SelectValue, SelectContent, SelectItem };
