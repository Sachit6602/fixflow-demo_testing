"use client"

import { useState, useEffect } from "react"
import { PageHeader } from "@/components/dashboard/page-header"
import { KpiCard } from "@/components/dashboard/kpi-card"
import { useDataSource } from "@/lib/data-context"
import {
  getKpiCustomers,
  getNewVsReturning,
  getTopPostcodes,
  getPeakHoursData,
  getCustomers,
} from "@/lib/data-provider"
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts"
import { cn } from "@/lib/utils"
import { Search, ArrowUpDown } from "lucide-react"

const HOURS = Array.from({ length: 24 }, (_, i) => i)

function getHeatColor(value: number, max: number) {
  if (value === 0) return "bg-secondary"
  const intensity = value / max
  if (intensity < 0.25) return "bg-blue-100 dark:bg-blue-900/30"
  if (intensity < 0.50) return "bg-blue-300 dark:bg-blue-700/50"
  if (intensity < 0.75) return "bg-blue-500 dark:bg-blue-600/70"
  return "bg-blue-700 dark:bg-blue-500"
}

export default function CustomersPage() {
  const { isLive } = useDataSource()
  const [kpi, setKpi] = useState<any>(null)
  const [nvr, setNvr] = useState<any[]>([])
  const [postcodes, setPostcodes] = useState<any[]>([])
  const [peakHours, setPeakHours] = useState<any[][]>([])
  const [customerList, setCustomerList] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const [search, setSearch] = useState("")
  const [sortBy, setSortBy] = useState<"name" | "totalSpent" | "totalQuotes">("totalSpent")
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([
      getKpiCustomers(isLive),
      getNewVsReturning(isLive),
      getTopPostcodes(isLive),
      getPeakHoursData(isLive),
      getCustomers(isLive),
    ]).then(([k, n, p, ph, c]) => {
      if (cancelled) return
      setKpi(k); setNvr(n); setPostcodes(p); setPeakHours(ph); setCustomerList(c)
      setLoading(false)
    })
    return () => { cancelled = true }
  }, [isLive])

  if (loading || !kpi) {
    return (
      <div className="p-6 max-w-[1400px] mx-auto">
        <PageHeader title="Customers" description="Customer behaviour and demographics" />
        <div className="text-muted-foreground text-sm">Loading...</div>
      </div>
    )
  }

  const maxHeat = Math.max(...peakHours.flatMap((d) => d.map((h: any) => h.value)), 1)

  const filtered = customerList
    .filter((c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.postcode.toLowerCase().includes(search.toLowerCase())
    )
    .sort((a, b) => {
      const aVal = a[sortBy]
      const bVal = b[sortBy]
      if (typeof aVal === "string" && typeof bVal === "string") {
        return sortDir === "asc" ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal)
      }
      return sortDir === "asc" ? (aVal as number) - (bVal as number) : (bVal as number) - (aVal as number)
    })

  function toggleSort(col: typeof sortBy) {
    if (sortBy === col) setSortDir(sortDir === "asc" ? "desc" : "asc")
    else { setSortBy(col); setSortDir("desc") }
  }

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      <PageHeader title="Customers" description="Customer behaviour and demographics" />

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <KpiCard title="Total Customers" value={kpi.totalCustomers.value} change={kpi.totalCustomers.change} />
        <KpiCard
          title="Returning Customers"
          value={kpi.returningCustomers.value}
          badge={{ label: `${kpi.returningCustomers.percentage}% of total`, variant: "blue" }}
        />
        <KpiCard title="Avg Quote Value" value={kpi.avgQuoteValue.value.toFixed(2)} prefix="£" change={kpi.avgQuoteValue.change} />
      </div>

      {/* New vs Returning + Top Postcodes */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
        {/* New vs Returning */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-foreground mb-4">New vs Returning</h2>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={nvr} cx="50%" cy="50%" innerRadius={50} outerRadius={80} dataKey="value" paddingAngle={4}>
                <Cell fill="var(--chart-1)" />
                <Cell fill="var(--chart-2)" />
              </Pie>
              <Legend iconSize={10} iconType="circle" formatter={(v) => <span className="text-xs text-foreground">{v}</span>} />
              <Tooltip
                contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: "8px", fontSize: "12px" }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Top Postcodes */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm lg:col-span-2">
          <h2 className="text-sm font-semibold text-foreground mb-4">Top Postcodes</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-xs text-muted-foreground font-medium py-2 pr-4">Postcode</th>
                  <th className="text-left text-xs text-muted-foreground font-medium py-2 pr-4">Area</th>
                  <th className="text-right text-xs text-muted-foreground font-medium py-2 pr-4">Customers</th>
                  <th className="text-right text-xs text-muted-foreground font-medium py-2">Revenue</th>
                </tr>
              </thead>
              <tbody>
                {postcodes.map((row) => (
                  <tr key={row.postcode} className="border-b border-border last:border-0 hover:bg-secondary/50 transition-colors">
                    <td className="py-2.5 pr-4 font-semibold text-primary">{row.postcode}</td>
                    <td className="py-2.5 pr-4 text-muted-foreground">{row.area}</td>
                    <td className="py-2.5 pr-4 text-right tabular-nums text-foreground">{row.count}</td>
                    <td className="py-2.5 text-right tabular-nums font-medium text-foreground">£{row.revenue.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Peak Hours Heatmap */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-sm mb-4">
        <h2 className="text-sm font-semibold text-foreground mb-1">Peak Chat Hours</h2>
        <p className="text-xs text-muted-foreground mb-4">Volume of chats initiated by day and hour</p>
        <div className="overflow-x-auto">
          <div className="min-w-[640px]">
            {/* Hour labels */}
            <div className="flex gap-0.5 ml-12 mb-1">
              {HOURS.map((h) => (
                <div key={h} className="flex-1 text-[9px] text-muted-foreground text-center">{h}h</div>
              ))}
            </div>
            {/* Grid */}
            {peakHours.map((dayData) => (
              <div key={dayData[0].day} className="flex items-center gap-0.5 mb-0.5">
                <div className="w-10 text-[11px] text-muted-foreground font-medium text-right pr-2 shrink-0">{dayData[0].day}</div>
                {dayData.map((cell) => (
                  <div
                    key={cell.hour}
                    className={cn("flex-1 aspect-square rounded-sm transition-colors", getHeatColor(cell.value, maxHeat))}
                    title={`${cell.day} ${cell.hour}:00 — ${cell.value} chats`}
                  />
                ))}
              </div>
            ))}
            {/* Legend */}
            <div className="flex items-center gap-2 mt-3 ml-12">
              <span className="text-[11px] text-muted-foreground">Low</span>
              <div className="flex gap-0.5">
                {["bg-secondary", "bg-blue-100 dark:bg-blue-900/30", "bg-blue-300 dark:bg-blue-700/50", "bg-blue-500 dark:bg-blue-600/70", "bg-blue-700 dark:bg-blue-500"].map((c, i) => (
                  <div key={i} className={cn("w-4 h-4 rounded-sm", c)} />
                ))}
              </div>
              <span className="text-[11px] text-muted-foreground">High</span>
            </div>
          </div>
        </div>
      </div>

      {/* Customer List */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
        <div className="flex items-center justify-between gap-4 mb-4">
          <h2 className="text-sm font-semibold text-foreground">Customer List</h2>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search name or postcode..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 pr-3 py-1.5 text-sm rounded-md border border-border bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring w-52"
            />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left text-xs text-muted-foreground font-medium py-2 pr-4">
                  <button className="flex items-center gap-1 hover:text-foreground" onClick={() => toggleSort("name")}>
                    Name <ArrowUpDown className="w-3 h-3" />
                  </button>
                </th>
                <th className="text-left text-xs text-muted-foreground font-medium py-2 pr-4">Postcode</th>
                <th className="text-left text-xs text-muted-foreground font-medium py-2 pr-4">First Seen</th>
                <th className="text-right text-xs text-muted-foreground font-medium py-2 pr-4">
                  <button className="flex items-center gap-1 hover:text-foreground ml-auto" onClick={() => toggleSort("totalQuotes")}>
                    Quotes <ArrowUpDown className="w-3 h-3" />
                  </button>
                </th>
                <th className="text-right text-xs text-muted-foreground font-medium py-2 pr-4">
                  <button className="flex items-center gap-1 hover:text-foreground ml-auto" onClick={() => toggleSort("totalSpent")}>
                    Spent <ArrowUpDown className="w-3 h-3" />
                  </button>
                </th>
                <th className="text-left text-xs text-muted-foreground font-medium py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr key={c.id} className="border-b border-border last:border-0 hover:bg-secondary/50 transition-colors">
                  <td className="py-3 pr-4 font-medium text-foreground">{c.name}</td>
                  <td className="py-3 pr-4 font-semibold text-primary">{c.postcode}</td>
                  <td className="py-3 pr-4 text-muted-foreground text-xs">{c.firstSeen}</td>
                  <td className="py-3 pr-4 text-right tabular-nums text-foreground">{c.totalQuotes}</td>
                  <td className="py-3 pr-4 text-right tabular-nums font-medium text-foreground">£{c.totalSpent.toLocaleString()}</td>
                  <td className="py-3">
                    <span className={cn(
                      "text-[11px] font-semibold px-2 py-0.5 rounded-full capitalize",
                      c.status === "returning"
                        ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400"
                        : "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                    )}>
                      {c.status}
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
