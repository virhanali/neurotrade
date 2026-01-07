import { useEffect, useRef } from 'react';
import { usePnLChart } from '@/hooks/useAdmin';
import { cn, formatCurrency } from '@/utils/helpers';
import { TrendingUp, TrendingDown, Loader2 } from 'lucide-react';

// We'll use a simple canvas chart instead of Chart.js for lighter bundle
export function PerformanceChart({ period = '24h' }: { period?: '24h' | '7d' }) {
    const { data, isLoading, error } = usePnLChart(period);
    const canvasRef = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        if (!data || !canvasRef.current) return;

        const canvas = canvasRef.current;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        // Clear canvas
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const chartData = data.data || [];
        // labels are included in data but not currently displayed on chart
        // const labels = data.labels || [];

        if (chartData.length === 0) return;

        const padding = 40;
        const width = canvas.width - padding * 2;
        const height = canvas.height - padding * 2;

        const maxVal = Math.max(...chartData, 0);
        const minVal = Math.min(...chartData, 0);
        const range = maxVal - minVal || 1;

        // Draw grid lines
        ctx.strokeStyle = '#e2e8f0';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) {
            const y = padding + (height / 4) * i;
            ctx.beginPath();
            ctx.moveTo(padding, y);
            ctx.lineTo(canvas.width - padding, y);
            ctx.stroke();
        }

        // Draw zero line if applicable
        if (minVal < 0 && maxVal > 0) {
            const zeroY = padding + height - ((0 - minVal) / range) * height;
            ctx.strokeStyle = '#94a3b8';
            ctx.lineWidth = 2;
            ctx.setLineDash([5, 5]);
            ctx.beginPath();
            ctx.moveTo(padding, zeroY);
            ctx.lineTo(canvas.width - padding, zeroY);
            ctx.stroke();
            ctx.setLineDash([]);
        }

        // Draw chart line
        const gradient = ctx.createLinearGradient(0, padding, 0, canvas.height - padding);
        const isPositive = chartData[chartData.length - 1] >= 0;

        if (isPositive) {
            gradient.addColorStop(0, 'rgba(16, 185, 129, 0.3)');
            gradient.addColorStop(1, 'rgba(16, 185, 129, 0)');
        } else {
            gradient.addColorStop(0, 'rgba(239, 68, 68, 0.3)');
            gradient.addColorStop(1, 'rgba(239, 68, 68, 0)');
        }

        // Draw area
        ctx.beginPath();
        ctx.moveTo(padding, canvas.height - padding);

        chartData.forEach((val: number, i: number) => {
            const x = padding + (i / (chartData.length - 1)) * width;
            const y = padding + height - ((val - minVal) / range) * height;
            if (i === 0) {
                ctx.lineTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        });

        ctx.lineTo(canvas.width - padding, canvas.height - padding);
        ctx.closePath();
        ctx.fillStyle = gradient;
        ctx.fill();

        // Draw line
        ctx.beginPath();
        chartData.forEach((val: number, i: number) => {
            const x = padding + (i / (chartData.length - 1)) * width;
            const y = padding + height - ((val - minVal) / range) * height;
            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        });
        ctx.strokeStyle = isPositive ? '#10b981' : '#ef4444';
        ctx.lineWidth = 2;
        ctx.stroke();

        // Draw dots at key points
        const lastVal = chartData[chartData.length - 1];
        const lastX = canvas.width - padding;
        const lastY = padding + height - ((lastVal - minVal) / range) * height;

        ctx.beginPath();
        ctx.arc(lastX, lastY, 5, 0, Math.PI * 2);
        ctx.fillStyle = isPositive ? '#10b981' : '#ef4444';
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();

    }, [data]);

    if (isLoading) {
        return (
            <div className="h-48 flex items-center justify-center">
                <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
            </div>
        );
    }

    if (error || !data?.data?.length) {
        return (
            <div className="h-48 flex flex-col items-center justify-center text-slate-500">
                <TrendingUp className="w-10 h-10 mb-2 opacity-30" />
                <p className="text-sm">No chart data yet</p>
                <p className="text-xs">Complete some trades to see performance</p>
            </div>
        );
    }

    const totalPnl = data.data[data.data.length - 1] || 0;
    const isPositive = totalPnl >= 0;

    return (
        <div>
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    {isPositive ? (
                        <TrendingUp className="w-5 h-5 text-emerald-500" />
                    ) : (
                        <TrendingDown className="w-5 h-5 text-rose-500" />
                    )}
                    <span className={cn(
                        'text-lg font-bold',
                        isPositive ? 'text-emerald-500' : 'text-rose-500'
                    )}>
                        {formatCurrency(totalPnl)}
                    </span>
                </div>
                <span className="text-xs text-slate-500 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded">
                    {period === '24h' ? 'Last 24 Hours' : 'Last 7 Days'}
                </span>
            </div>
            <canvas
                ref={canvasRef}
                width={400}
                height={180}
                className="w-full"
            />
        </div>
    );
}
