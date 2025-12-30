import { HTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";
import { ChevronUp, ChevronDown } from "lucide-react";

interface TableColumn<T = any> {
    key: string;
    title: string;
    width?: string;
    sortable?: boolean;
    align?: "left" | "center" | "right";
    render?: (value: any, row: T, index: number) => React.ReactNode;
}

interface TableProps<T = any> extends HTMLAttributes<HTMLDivElement> {
    columns: TableColumn<T>[];
    data: T[];
    loading?: boolean;
    striped?: boolean;
    hover?: boolean;
    compact?: boolean;
    emptyMessage?: string;
    onSort?: (key: string, direction: "asc" | "desc" | null) => void;
    sortKey?: string;
    sortDirection?: "asc" | "desc" | null;
    onRowClick?: (row: T) => void;
}

const Table = forwardRef<HTMLDivElement, TableProps>(
    ({
        columns,
        data,
        loading = false,
        striped = true,
        hover = false,
        compact = true,
        emptyMessage = "데이터가 없습니다.",
        onSort,
        sortKey,
        sortDirection,
        onRowClick,
        className,
        ...props
    }, ref) => {
        const handleSort = (key: string) => {
            if (!onSort) return;

            let newDirection: "asc" | "desc" | null = "asc";
            if (sortKey === key) {
                if (sortDirection === "asc") {
                    newDirection = "desc";
                } else if (sortDirection === "desc") {
                    newDirection = null;
                }
            }

            onSort(key, newDirection);
        };

        const getSortIcon = (key: string) => {
            if (sortKey !== key) return null;
            if (sortDirection === "asc") return <ChevronUp className="h-3.5 w-3.5" />;
            if (sortDirection === "desc") return <ChevronDown className="h-3.5 w-3.5" />;
            return null;
        };

        const rowHeight = compact ? "h-9" : "h-11";
        const cellPadding = compact ? "px-3 py-2" : "px-4 py-2.5";
        const fontSize = compact ? "text-sm" : "text-base";

        return (
            <div ref={ref} className={cn("w-full overflow-auto table-scroll max-h-[600px]", className)} {...props}>
                <table className="w-full border-collapse caption-bottom relative">
                    <thead className="bg-muted/90 backdrop-blur-sm border-b border-border sticky top-0 z-10 shadow-sm">
                        <tr>
                            {columns.map((column) => (
                                <th
                                    key={column.key}
                                    className={cn(
                                        "h-9 px-3 py-2 text-left font-semibold text-foreground border-b border-border whitespace-nowrap",
                                        column.align === "center" && "text-center",
                                        column.align === "right" && "text-right",
                                        column.sortable && "cursor-pointer hover:bg-muted/80 select-none",
                                        column.width && column.width
                                    )}
                                    onClick={() => column.sortable && handleSort(column.key)}
                                    style={{ width: column.width }}
                                >
                                    <div className="flex items-center gap-1">
                                        <span className="text-[12px] uppercase tracking-wider">{column.title}</span>
                                        {getSortIcon(column.key)}
                                    </div>
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className={cn(
                        striped && "[&_tr:nth-child(even)]:bg-muted/30",
                        hover && "[&_tr:hover]:bg-muted/60"
                    )}>
                        {loading ? (
                            <tr>
                                <td colSpan={columns.length} className={cn("text-center py-8 text-muted-foreground", rowHeight, fontSize)}>
                                    <div className="flex items-center justify-center gap-2">
                                        <div className="h-4 w-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                                        <span>로딩 중...</span>
                                    </div>
                                </td>
                            </tr>
                        ) : data.length === 0 ? (
                            <tr>
                                <td colSpan={columns.length} className={cn("text-center py-12 text-muted-foreground", rowHeight, fontSize)}>
                                    {emptyMessage}
                                </td>
                            </tr>
                        ) : (
                            data.map((row, rowIndex) => (
                                <tr
                                    key={rowIndex}
                                    className={cn(
                                        "border-b border-border/50 transition-colors",
                                        onRowClick && "cursor-pointer hover:bg-muted/80",
                                        rowHeight
                                    )}
                                    onClick={() => onRowClick?.(row)}
                                >
                                    {columns.map((column) => (
                                        <td
                                            key={column.key}
                                            className={cn(
                                                cellPadding,
                                                fontSize,
                                                "text-foreground",
                                                column.align === "center" && "text-center",
                                                column.align === "right" && "text-right"
                                            )}
                                        >
                                            {column.render
                                                ? column.render(row[column.key], row, rowIndex)
                                                : row[column.key]
                                            }
                                        </td>
                                    ))}
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>
        );
    }
);

/**
 * 전형적인 ERP용 CSV 내보내기 유틸리티
 */
export const exportToCSV = (data: any[], columns: TableColumn[], filename: string) => {
    const headers = columns.map(col => col.title).join(',');
    const rows = data.map(row => {
        return columns.map(col => {
            const val = row[col.key];
            if (val === null || val === undefined) return '';
            const escaped = String(val).replace(/"/g, '""');
            return `"${escaped}"`;
        }).join(',');
    });

    const csvContent = "data:text/csv;charset=utf-8,\uFEFF" + [headers, ...rows].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `${filename}_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
};

Table.displayName = "Table";

export { Table };
export type { TableColumn, TableProps };
