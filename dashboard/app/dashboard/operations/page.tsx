"use client"

import { PageHeader } from "@/components/dashboard/page-header"
import { KpiCard } from "@/components/dashboard/kpi-card"
import {
  kpiOperations,
  negotiationStats,
  safetyLog,
  jobTypeVolume,
} from "@/lib/sample-data"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts"
import { cn } from "@/lib/utils"

const triggerStyles: Record<string, string> = {
  "Gas Smell": "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  "Authority Block": "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  "Prompt Injection": "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  "Out-of-scope Brand": "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  "Out-of-scope Location": "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
}

const actionStyles: Record<string, string> = {
  "Hard Stop": "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  "Human Review": "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  "Escalation": "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
}

function StatRow({ label, value, unit, note }: { label: string; value: number | string; unit?: string; note?: string }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-border last:border-0">
      <div>
        <div className="text-sm font-medium text-foreground">{label}</div>
        {note && <div className="text-xs text-muted-foreground">{note}</div>}
      </div>
      <div className="text-lg font-bold text-foreground tabular-nums">
        {value}{unit && <span className="text-sm font-normal text-muted-foreground ml-0.5">{unit}</span>}
      </div>
    </div>
  )
}

export default function OperationsPage() {
  const maxJobVolume = Math.max(...jobTypeVolume.map((j) => j.value))

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      <PageHeader title="Operations" description="Agent performance, safety events, and job breakdown" />

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
        <KpiCard
          title="Avg Response Time"
          value={kpiOperations.avgResponseTime.value}
          suffix="sec"
          change={kpiOperations.avgResponseTime.change}
          badge={{ label: "↓ improving", variant: "green" }}
        />
        <KpiCard
          title="Safety Triggers"
          value={kpiOperations.safetyTriggers.value}
          badge={{ label: "amber alert", variant: "amber" }}
        />
        <KpiCard
          title="Escalations"
          value={kpiOperations.escalations.value}
          badge={{ label: `+${kpiOperations.escalations.change} vs last week`, variant: "amber" }}
        />
        <KpiCard
          title="Out-of-Scope Requests"
          value={kpiOperations.outOfScope.value}
          badge={{ label: `${kpiOperations.outOfScope.change} vs last week`, variant: "green" }}
        />
      </div>

      {/* Negotiation Stats + Job Type Volume */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        {/* Negotiation Stats */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-foreground mb-4">Negotiation Statistics</h2>
          <StatRow
            label="Pushback Rate"
            value={`${negotiationStats.pushbackRate}%`}
            note="Quotes where customer challenged the price"
          />
          <StatRow
            label="Average Discount Given"
            value={`${negotiationStats.avgDiscountGiven}%`}
            note="Mean discount across all negotiated quotes"
          />
          <StatRow
            label="Floor Price Hit Rate"
            value={`${negotiationStats.floorPriceHitRate}%`}
            note="Negotiations that reached the minimum floor price"
          />
          <StatRow
            label="Competitor Match Attempts"
            value={negotiationStats.competitorMatchAttempts}
            note="Customers who mentioned a competitor price"
          />

          {/* Mini visual breakdown */}
          <div className="mt-4 pt-4 border-t border-border">
            <p className="text-xs text-muted-foreground mb-3">Quote outcome breakdown</p>
            <div className="flex h-4 rounded-full overflow-hidden gap-0.5">
              <div className="bg-primary" style={{ width: "53%" }} title="Accepted" />
              <div className="bg-chart-2" style={{ width: "28%" }} title="Negotiated & accepted" />
              <div className="bg-amber-400" style={{ width: "11%" }} title="Rejected" />
              <div className="bg-border" style={{ width: "8%" }} title="Abandoned" />
            </div>
            <div className="flex gap-4 mt-2">
              {[
                { label: "Accepted", color: "bg-primary", pct: "53%" },
                { label: "Negotiated", color: "bg-chart-2", pct: "28%" },
                { label: "Rejected", color: "bg-amber-400", pct: "11%" },
                { label: "Abandoned", color: "bg-border", pct: "8%" },
              ].map((item) => (
                <div key={item.label} className="flex items-center gap-1.5">
                  <div className={cn("w-2.5 h-2.5 rounded-sm", item.color)} />
                  <span className="text-[11px] text-muted-foreground">{item.label} {item.pct}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Job Type Volume */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-foreground mb-4">Job Type Volume</h2>
          <div className="flex flex-col gap-2.5">
            {jobTypeVolume.map((job) => (
              <div key={job.name}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-muted-foreground">{job.name}</span>
                  <span className="text-xs font-semibold text-foreground tabular-nums">{job.value}</span>
                </div>
                <div className="h-5 rounded bg-secondary overflow-hidden">
                  <div
                    className="h-full rounded bg-primary/80 transition-all"
                    style={{ width: `${(job.value / maxJobVolume) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Safety & Escalation Log */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-foreground mb-1">Safety & Escalation Log</h2>
        <p className="text-xs text-muted-foreground mb-4">Recent safety triggers, escalations, and out-of-scope events</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left text-xs text-muted-foreground font-medium py-2 pr-4 w-36">Time</th>
                <th className="text-left text-xs text-muted-foreground font-medium py-2 pr-4">Customer</th>
                <th className="text-left text-xs text-muted-foreground font-medium py-2 pr-4">Trigger</th>
                <th className="text-left text-xs text-muted-foreground font-medium py-2 pr-4 w-64">Message</th>
                <th className="text-left text-xs text-muted-foreground font-medium py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {safetyLog.map((row) => (
                <tr key={row.id} className="border-b border-border last:border-0 hover:bg-secondary/50 transition-colors">
                  <td className="py-3 pr-4 text-xs text-muted-foreground tabular-nums whitespace-nowrap">{row.time}</td>
                  <td className="py-3 pr-4 text-foreground font-medium">{row.customer}</td>
                  <td className="py-3 pr-4">
                    <span className={cn("text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap", triggerStyles[row.trigger] ?? "bg-secondary text-foreground")}>
                      {row.trigger}
                    </span>
                  </td>
                  <td className="py-3 pr-4 text-xs text-muted-foreground max-w-xs">
                    <span className="block truncate max-w-[260px]" title={row.message}>"{row.message}"</span>
                  </td>
                  <td className="py-3">
                    <span className={cn("text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap", actionStyles[row.action] ?? "bg-secondary text-foreground")}>
                      {row.action}
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
