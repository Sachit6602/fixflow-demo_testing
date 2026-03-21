"use client"

import { PageHeader } from "@/components/dashboard/page-header"
import { KpiCard } from "@/components/dashboard/kpi-card"
import {
  kpiOverview,
  sparklineData,
  conversionFunnel,
  revenueTrend,
  revenueByJobType,
  recentActivity,
} from "@/lib/sample-data"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts"
import { cn } from "@/lib/utils"

const statusStyles: Record<string, string> = {
  completed: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  "pending review": "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  escalated: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  blocked: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
}

const CHART_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
]

export default function OverviewPage() {
  const maxFunnelValue = conversionFunnel[0].value

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      <PageHeader
        title="Overview"
        description="Last 30 days performance summary"
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
        <KpiCard
          title="Chats Initiated"
          value={kpiOverview.chatsInitiated.value}
          change={kpiOverview.chatsInitiated.change}
          sparkline={sparklineData.chatsInitiated}
        />
        <KpiCard
          title="Quotes Sent"
          value={kpiOverview.quotesSent.value}
          change={kpiOverview.quotesSent.change}
          sparkline={sparklineData.quotesSent}
        />
        <KpiCard
          title="Quotes Accepted"
          value={kpiOverview.quotesAccepted.value}
          change={kpiOverview.quotesAccepted.change}
          sparkline={sparklineData.quotesAccepted}
        />
        <KpiCard
          title="Revenue"
          value={kpiOverview.revenue.value.toLocaleString()}
          change={kpiOverview.revenue.change}
          prefix="£"
          sparkline={sparklineData.revenue}
        />
      </div>

      {/* Conversion Funnel + Revenue by Job Type */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
        {/* Funnel */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-foreground mb-4">Conversion Funnel</h2>
          <div className="flex flex-col gap-3">
            {conversionFunnel.map((stage, i) => (
              <div key={stage.stage}>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-sm text-muted-foreground">{stage.stage}</span>
                  <span className="text-sm font-semibold text-foreground tabular-nums">{stage.value.toLocaleString()}</span>
                </div>
                <div className="h-7 rounded-md bg-secondary overflow-hidden">
                  <div
                    className="h-full rounded-md bg-primary transition-all"
                    style={{ width: `${(stage.value / maxFunnelValue) * 100}%` }}
                  />
                </div>
                {stage.dropoff !== null && (
                  <div className="text-[11px] text-red-500 dark:text-red-400 mt-1 text-right">
                    ▼ {stage.dropoff}% drop-off
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Revenue by job type */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm lg:col-span-2">
          <h2 className="text-sm font-semibold text-foreground mb-4">Revenue by Job Type</h2>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={revenueByJobType}
                cx="40%"
                cy="50%"
                innerRadius={55}
                outerRadius={90}
                dataKey="value"
                paddingAngle={3}
              >
                {revenueByJobType.map((_, index) => (
                  <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Legend
                layout="vertical"
                align="right"
                verticalAlign="middle"
                iconSize={10}
                iconType="circle"
                formatter={(value) => <span className="text-xs text-foreground">{value}</span>}
              />
              <Tooltip
                formatter={(value: number) => [`£${value.toLocaleString()}`, "Revenue"]}
                contentStyle={{
                  background: "var(--card)",
                  border: "1px solid var(--border)",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Revenue trend */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-sm mb-4">
        <h2 className="text-sm font-semibold text-foreground mb-4">Daily Revenue — Last 30 Days</h2>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={revenueTrend} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              tickLine={false}
              axisLine={false}
              interval={4}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `£${v}`}
              width={50}
            />
            <Tooltip
              formatter={(v: number) => [`£${v.toLocaleString()}`, "Revenue"]}
              contentStyle={{
                background: "var(--card)",
                border: "1px solid var(--border)",
                borderRadius: "8px",
                fontSize: "12px",
              }}
            />
            <Line
              type="monotone"
              dataKey="revenue"
              stroke="var(--primary)"
              strokeWidth={2.5}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Recent Activity */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-foreground mb-4">Recent Activity</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left text-xs text-muted-foreground font-medium py-2 pr-4 w-20">Time</th>
                <th className="text-left text-xs text-muted-foreground font-medium py-2 pr-4">Customer</th>
                <th className="text-left text-xs text-muted-foreground font-medium py-2 pr-4">Event</th>
                <th className="text-right text-xs text-muted-foreground font-medium py-2 pr-4">Amount</th>
                <th className="text-left text-xs text-muted-foreground font-medium py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {recentActivity.map((item) => (
                <tr key={item.id} className="border-b border-border last:border-0 hover:bg-secondary/50 transition-colors">
                  <td className="py-3 pr-4 text-muted-foreground tabular-nums text-xs">{item.time}</td>
                  <td className="py-3 pr-4 text-foreground font-medium">{item.customer}</td>
                  <td className="py-3 pr-4 text-muted-foreground">{item.event}</td>
                  <td className="py-3 pr-4 text-right font-medium tabular-nums">
                    {item.amount !== null ? <span className="text-foreground">£{item.amount}</span> : <span className="text-muted-foreground">—</span>}
                  </td>
                  <td className="py-3">
                    <span className={cn("text-[11px] font-semibold px-2 py-0.5 rounded-full capitalize", statusStyles[item.status])}>
                      {item.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
