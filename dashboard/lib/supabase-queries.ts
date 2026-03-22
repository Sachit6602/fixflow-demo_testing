import { supabase } from "./supabase"

// ── Overview page ─────────────────────────────────────────────────────────────

export async function getKpiOverview() {
  const chatsResult = await supabase
    .from("chats")
    .select("*", { count: "exact", head: true })
  console.log("[Supabase] chats:", chatsResult.count, chatsResult.error?.message)

  const quotesResult = await supabase
    .from("quote_history")
    .select("*", { count: "exact", head: true })
  console.log("[Supabase] quotes:", quotesResult.count, quotesResult.error?.message)

  const acceptedResult = await supabase
    .from("quote_history")
    .select("*", { count: "exact", head: true })
    .eq("accepted", true)

  const { data: revenueData } = await supabase
    .from("quote_history")
    .select("paid_amount")
    .eq("accepted", true)

  const revenue = (revenueData || []).reduce((sum, q) => sum + (q.paid_amount || 0), 0)

  return {
    chatsInitiated: { value: chatsResult.count || 0, change: 0 },
    quotesSent: { value: quotesResult.count || 0, change: 0 },
    quotesAccepted: { value: acceptedResult.count || 0, change: 0 },
    revenue: { value: Math.round(revenue * 100) / 100, change: 0 },
  }
}

export async function getConversionFunnel() {
  const { count: chats } = await supabase
    .from("chats")
    .select("*", { count: "exact", head: true })

  const { count: quotes } = await supabase
    .from("quote_history")
    .select("*", { count: "exact", head: true })

  const { count: accepted } = await supabase
    .from("quote_history")
    .select("*", { count: "exact", head: true })
    .eq("accepted", true)

  const { count: paid } = await supabase
    .from("quote_history")
    .select("*", { count: "exact", head: true })
    .not("tx_ref", "is", null)

  const c = chats || 0
  const q = quotes || 0
  const a = accepted || 0
  const p = paid || 0

  return [
    { stage: "Chats Initiated", value: c, dropoff: null },
    { stage: "Quotes Sent", value: q, dropoff: c > 0 ? Math.round(((c - q) / c) * 1000) / 10 : 0 },
    { stage: "Quotes Accepted", value: a, dropoff: q > 0 ? Math.round(((q - a) / q) * 1000) / 10 : 0 },
    { stage: "Paid", value: p, dropoff: a > 0 ? Math.round(((a - p) / a) * 1000) / 10 : 0 },
  ]
}

export async function getRevenueTrend() {
  const thirtyDaysAgo = new Date(Date.now() - 30 * 86400000).toISOString()
  const { data } = await supabase
    .from("quote_history")
    .select("created_at, paid_amount")
    .eq("accepted", true)
    .gte("created_at", thirtyDaysAgo)
    .order("created_at")

  // Group by date
  const byDate: Record<string, number> = {}
  for (let i = 0; i < 30; i++) {
    const d = new Date(Date.now() - (29 - i) * 86400000)
    const key = d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })
    byDate[key] = 0
  }
  for (const row of data || []) {
    const d = new Date(row.created_at)
    const key = d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })
    if (key in byDate) byDate[key] += row.paid_amount || 0
  }

  return Object.entries(byDate).map(([date, revenue]) => ({
    date,
    revenue: Math.round(revenue * 10) / 10,
  }))
}

export async function getRevenueByJobType() {
  const { data } = await supabase
    .from("quote_history")
    .select("job_type, paid_amount")
    .eq("accepted", true)

  const byType: Record<string, number> = {}
  for (const row of data || []) {
    const type = (row.job_type || "unknown").replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase())
    byType[type] = (byType[type] || 0) + (row.paid_amount || 0)
  }

  const colors = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"]
  return Object.entries(byType).map(([name, value], i) => ({
    name,
    value: Math.round(value),
    color: colors[i % colors.length],
  }))
}

export async function getRecentActivity() {
  const { data } = await supabase
    .from("events")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(10)

  const eventLabels: Record<string, string> = {
    chat_started: "Chat Started",
    quote_issued: "Quote Sent",
    quote_accepted: "Quote Accepted",
    payment_confirmed: "Payment Confirmed",
    safety_trigger: "Safety Trigger",
    escalation: "Escalation",
    out_of_scope: "Out of Scope",
    negotiation_round: "Negotiation",
    chat_ended: "Chat Ended",
  }

  const statusMap: Record<string, string> = {
    chat_started: "pending review",
    quote_issued: "pending review",
    quote_accepted: "completed",
    payment_confirmed: "completed",
    safety_trigger: "escalated",
    escalation: "blocked",
    out_of_scope: "escalated",
    negotiation_round: "pending review",
    chat_ended: "completed",
  }

  return (data || []).map((e, i) => {
    const detail = typeof e.detail === "string" ? JSON.parse(e.detail) : (e.detail || {})
    const time = new Date(e.created_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
    return {
      id: e.id || i + 1,
      time,
      customer: detail.customer_name || "Customer",
      event: eventLabels[e.event_type] || e.event_type,
      amount: detail.final_price || detail.amount || null,
      status: statusMap[e.event_type] || "pending review",
    }
  })
}

// ── Customers page ────────────────────────────────────────────────────────────

export async function getKpiCustomers() {
  const { count: totalCount } = await supabase
    .from("users")
    .select("*", { count: "exact", head: true })

  const { data: returningData } = await supabase
    .from("users")
    .select("total_quotes")
    .gt("total_quotes", 1)

  const returningCount = returningData?.length || 0
  const total = totalCount || 0

  const { data: quoteData } = await supabase
    .from("quote_history")
    .select("final_price")

  const prices = (quoteData || []).map(q => q.final_price).filter(Boolean)
  const avgQuote = prices.length > 0 ? prices.reduce((a, b) => a + b, 0) / prices.length : 0

  return {
    totalCustomers: { value: total, change: 0 },
    returningCustomers: { value: returningCount, percentage: total > 0 ? Math.round((returningCount / total) * 1000) / 10 : 0 },
    avgQuoteValue: { value: Math.round(avgQuote * 100) / 100, change: 0 },
  }
}

export async function getNewVsReturning() {
  const { count: total } = await supabase
    .from("users")
    .select("*", { count: "exact", head: true })

  const { data: returning } = await supabase
    .from("users")
    .select("total_quotes")
    .gt("total_quotes", 1)

  const ret = returning?.length || 0
  const tot = total || 0

  return [
    { name: "New", value: tot - ret },
    { name: "Returning", value: ret },
  ]
}

export async function getTopPostcodes() {
  const { data } = await supabase
    .from("quote_history")
    .select("postcode, paid_amount, accepted")

  const byPostcode: Record<string, { count: number; revenue: number }> = {}
  for (const row of data || []) {
    const pc = (row.postcode || "Unknown").split(" ")[0].toUpperCase()
    if (!byPostcode[pc]) byPostcode[pc] = { count: 0, revenue: 0 }
    byPostcode[pc].count++
    if (row.accepted) byPostcode[pc].revenue += row.paid_amount || 0
  }

  return Object.entries(byPostcode)
    .map(([postcode, { count, revenue }]) => ({
      postcode,
      area: "",
      count,
      revenue: Math.round(revenue),
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 10)
}

export async function getPeakHoursData() {
  const { data } = await supabase
    .from("chats")
    .select("started_at")

  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
  const grid: Record<string, Record<number, number>> = {}
  for (const day of days) {
    grid[day] = {}
    for (let h = 0; h < 24; h++) grid[day][h] = 0
  }

  for (const row of data || []) {
    const d = new Date(row.started_at)
    const day = days[d.getDay() === 0 ? 6 : d.getDay() - 1]
    const hour = d.getHours()
    grid[day][hour]++
  }

  return days.map((day) =>
    Array.from({ length: 24 }, (_, h) => ({
      day,
      hour: h,
      value: grid[day][h],
    }))
  )
}

export async function getCustomers() {
  const { data } = await supabase
    .from("users")
    .select("*")
    .order("last_seen", { ascending: false })

  return (data || []).map((u, i) => ({
    id: i + 1,
    name: u.customer_name || "Customer",
    postcode: "",
    firstSeen: new Date(u.first_seen).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }),
    totalQuotes: u.total_quotes || 0,
    totalSpent: 0,
    status: (u.total_quotes || 0) > 1 ? "returning" : "new",
  }))
}

// ── Operations page ───────────────────────────────────────────────────────────

export async function getKpiOperations() {
  const { data: chatData } = await supabase
    .from("chats")
    .select("response_time_seconds")
    .not("response_time_seconds", "is", null)

  const times = (chatData || []).map(c => c.response_time_seconds).filter(Boolean)
  const avgResponse = times.length > 0 ? Math.round(times.reduce((a, b) => a + b, 0) / times.length) : 0

  const { count: safetyCount } = await supabase
    .from("events")
    .select("*", { count: "exact", head: true })
    .eq("event_type", "safety_trigger")

  const { count: escalationCount } = await supabase
    .from("events")
    .select("*", { count: "exact", head: true })
    .eq("event_type", "escalation")

  const { count: outOfScopeCount } = await supabase
    .from("events")
    .select("*", { count: "exact", head: true })
    .eq("event_type", "out_of_scope")

  return {
    avgResponseTime: { value: avgResponse, unit: "sec", change: 0 },
    safetyTriggers: { value: safetyCount || 0, severity: (safetyCount || 0) > 5 ? "red" : "amber" },
    escalations: { value: escalationCount || 0, change: 0 },
    outOfScope: { value: outOfScopeCount || 0, change: 0 },
  }
}

export async function getNegotiationStats() {
  const { data: negEvents } = await supabase
    .from("events")
    .select("detail")
    .eq("event_type", "negotiation_round")

  const { count: totalQuotes } = await supabase
    .from("quote_history")
    .select("*", { count: "exact", head: true })

  const rounds = (negEvents || []).map(e =>
    typeof e.detail === "string" ? JSON.parse(e.detail) : (e.detail || {})
  )

  const pushbackCount = rounds.length
  const pushbackRate = (totalQuotes || 0) > 0 ? Math.round((pushbackCount / (totalQuotes || 1)) * 1000) / 10 : 0
  const discounts = rounds.map(r => r.discount_pct || 0).filter(Boolean)
  const avgDiscount = discounts.length > 0 ? Math.round((discounts.reduce((a, b) => a + b, 0) / discounts.length) * 10) / 10 : 0
  const floorHits = rounds.filter(r => r.floor_hit).length
  const floorRate = pushbackCount > 0 ? Math.round((floorHits / pushbackCount) * 1000) / 10 : 0
  const competitorMatches = rounds.filter(r => r.competitor_match).length

  return {
    pushbackRate,
    avgDiscountGiven: avgDiscount,
    floorPriceHitRate: floorRate,
    competitorMatchAttempts: competitorMatches,
  }
}

export async function getSafetyLog() {
  const { data } = await supabase
    .from("events")
    .select("*")
    .in("event_type", ["safety_trigger", "escalation", "out_of_scope"])
    .order("created_at", { ascending: false })
    .limit(10)

  const triggerLabels: Record<string, string> = {
    safety_trigger: "Safety Trigger",
    escalation: "Authority Block",
    out_of_scope: "Out of Scope",
  }

  const actionLabels: Record<string, string> = {
    safety_trigger: "Hard Stop",
    escalation: "Human Review",
    out_of_scope: "Escalation",
  }

  return (data || []).map((e, i) => {
    const detail = typeof e.detail === "string" ? JSON.parse(e.detail) : (e.detail || {})
    const time = new Date(e.created_at).toLocaleString("en-GB", {
      day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
    })
    return {
      id: e.id || i + 1,
      time,
      customer: e.luffa_uid ? `User ${e.luffa_uid.slice(0, 6)}` : "Customer",
      trigger: triggerLabels[e.event_type] || e.event_type,
      message: detail.safety_type || detail.reason || detail.job_type || "",
      action: actionLabels[e.event_type] || "Escalation",
    }
  })
}

export async function getJobTypeVolume() {
  const { data } = await supabase
    .from("quote_history")
    .select("job_type")

  const byType: Record<string, number> = {}
  for (const row of data || []) {
    const type = (row.job_type || "unknown").replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase())
    byType[type] = (byType[type] || 0) + 1
  }

  return Object.entries(byType).map(([name, value]) => ({ name, value }))
}
