import { ShoppingBag, CheckCircle, Clock, Zap } from "lucide-react";
import { Table, TableColumn } from "@/components/ui/Table";

interface StatData {
    label: string;
    value: number | string;
    icon: React.ReactNode;
    progress?: number;
    description?: string;
    trend?: string;
}

interface StatTableProps {
    title: string;
    data: StatData[];
}

export function StatTable({ title, data }: StatTableProps) {
    const columns: TableColumn<StatData>[] = [
        {
            key: "label",
            title: "항목",
            width: "25%",
            render: (value, row) => (
                <div className="flex items-center gap-2">
                    <div className="h-5 w-5 rounded-sm bg-primary/10 flex items-center justify-center">
                        {row.icon}
                    </div>
                    <span className="text-[11px]">{value}</span>
                </div>
            ),
        },
        {
            key: "value",
            title: "값",
            align: "right",
            width: "20%",
            render: (value) => (
                <span className="font-semibold text-xs">
                    {typeof value === 'number' ? value.toLocaleString() : value}
                </span>
            ),
        },
        {
            key: "progress",
            title: "진행률",
            align: "right",
            width: "25%",
            render: (value) => {
                if (value === undefined) return <span className="text-muted-foreground text-xs">-</span>;
                return (
                    <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-muted rounded-sm overflow-hidden max-w-[80px]">
                            <div
                                className="h-full bg-primary transition-all"
                                style={{ width: `${value}%` }}
                            />
                        </div>
                        <span className="text-[10px] font-medium text-muted-foreground w-8">
                            {Math.round(value)}%
                        </span>
                    </div>
                );
            },
        },
        {
            key: "description",
            title: "설명",
            width: "30%",
            render: (value) => (
                <span className="text-[10px] text-muted-foreground leading-tight">
                    {value}
                </span>
            ),
        },
    ];

    return (
        <div className="border border-border rounded-sm bg-card">
            <div className="px-3 py-1.5 border-b border-border bg-muted/50">
                <span className="text-[11px] font-semibold text-foreground">{title}</span>
            </div>
            <div className="p-2">
                <Table
                    columns={columns}
                    data={data}
                    compact={true}
                    striped={true}
                    hover={false}
                />
            </div>
        </div>
    );
}

export function OverallStats({ stats, dashboardStats }: any) {
    const data: StatData[] = [
        {
            label: "전체 수집 상품",
            value: dashboardStats?.products?.total_raw || stats.total,
            icon: <ShoppingBag className="h-3 w-3 text-primary" />,
            progress: 100,
            description: "공급사로부터 수집된 전체 원본 데이터",
        },
        {
            label: "가공 대기 상품",
            value: dashboardStats?.products?.pending || stats.pending,
            icon: <Clock className="h-3 w-3 text-warning" />,
            progress: stats.total > 0 ? (stats.pending / stats.total) * 100 : 0,
            description: "AI 분석 및 가공을 기다리는 상품",
        },
        {
            label: "판매 중인 상품",
            value: dashboardStats?.products?.completed || stats.completed,
            icon: <CheckCircle className="h-3 w-3 text-success" />,
            progress: stats.total > 0 ? (stats.completed / stats.total) * 100 : 0,
            description: "마켓 등록이 완료되어 판매 중인 상품",
        },
        {
            label: "결제 완료 주문",
            value: dashboardStats?.orders?.payment_completed || 0,
            icon: <Zap className="h-3 w-3 text-info" />,
            description: "오늘 발생한 신규 주문 건수",
            trend: "+12%",
        },
    ];

    return <StatTable title="종합 현황" data={data} />;
}
