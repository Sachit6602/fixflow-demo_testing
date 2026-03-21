import { cn } from "@/lib/utils"
import { TrendingUp, TrendingDown } from "lucide-react"
import { ResponsiveContainer, LineChart, Line } from "recharts"

interface KpiCardProps {
  title: string
  value: string | number
  change?: number
  sparkline?: number[]
  suffix?: string
  prefix?: string
  badge?: { label: string; variant: "red" | "amber" | "green" | "blue" }
}

export function KpiCard({ title, value, change, sparkline, suffix, prefix, badge }: KpiCardProps) {
  const isPositive = change !== undefined && change >= 0
  const sparkData = sparkline?.map((v, i) => ({ v, i }))

  return (
    <div className="bg-card border border-border rounded-xl p-5 flex flex-col gap-3 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm text-muted-foreground font-medium">{title}</span>
        {badge && (
          <span className={cn(
            "text-[11px] font-semibold px-2 py-0.5 rounded-full",
            badge.variant === "red" && "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
            badge.variant === "amber" && "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
            badge.variant === "green" && "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
            badge.variant === "blue" && "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
          )}>
            {badge.label}
          </span>
        )}
      </div>

      <div className="flex items-end justify-between gap-2">
        <div>
          <div className="flex items-baseline gap-0.5">
            {prefix && <span className="text-xl font-semibold text-muted-foreground">{prefix}</span>}
            <span className="text-3xl font-bold text-foreground tabular-nums">{typeof value === "number" ? value.toLocaleString() : value}</span>
            {suffix && <span className="text-sm text-muted-foreground ml-1">{suffix}</span>}
          </div>
          {change !== undefined && (
            <div className={cn("flex items-center gap-1 mt-1 text-xs font-medium", isPositive ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400")}>
              {isPositive ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
              <span>{isPositive ? "+" : ""}{change}% vs last period</span>
            </div>
          )}
        </div>

        {sparkData && (
          <div className="w-24 h-12 shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sparkData}>
                <Line
                  type="monotone"
                  dataKey="v"
                  stroke="var(--primary)"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  )
}
