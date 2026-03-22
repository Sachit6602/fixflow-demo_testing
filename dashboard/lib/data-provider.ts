import * as sample from "./sample-data"
import * as live from "./supabase-queries"

// Each function takes isLive flag and returns the appropriate data source.
// Sample data is returned synchronously (wrapped in Promise.resolve),
// live data is fetched from Supabase.

// ── Overview ──────────────────────────────────────────────────────────────────

export async function getKpiOverview(isLive: boolean) {
  if (isLive) return live.getKpiOverview()
  return sample.kpiOverview
}

export async function getSparklineData(isLive: boolean) {
  // No live sparkline — return sample for both
  return sample.sparklineData
}

export async function getConversionFunnel(isLive: boolean) {
  if (isLive) return live.getConversionFunnel()
  return sample.conversionFunnel
}

export async function getRevenueTrend(isLive: boolean) {
  if (isLive) return live.getRevenueTrend()
  return sample.revenueTrend
}

export async function getRevenueByJobType(isLive: boolean) {
  if (isLive) return live.getRevenueByJobType()
  return sample.revenueByJobType
}

export async function getRecentActivity(isLive: boolean) {
  if (isLive) return live.getRecentActivity()
  return sample.recentActivity
}

// ── Customers ─────────────────────────────────────────────────────────────────

export async function getKpiCustomers(isLive: boolean) {
  if (isLive) return live.getKpiCustomers()
  return sample.kpiCustomers
}

export async function getNewVsReturning(isLive: boolean) {
  if (isLive) return live.getNewVsReturning()
  return sample.newVsReturning
}

export async function getTopPostcodes(isLive: boolean) {
  if (isLive) return live.getTopPostcodes()
  return sample.topPostcodes
}

export async function getPeakHoursData(isLive: boolean) {
  if (isLive) return live.getPeakHoursData()
  return sample.peakHoursData
}

export async function getCustomers(isLive: boolean) {
  if (isLive) return live.getCustomers()
  return sample.customers
}

// ── Operations ────────────────────────────────────────────────────────────────

export async function getKpiOperations(isLive: boolean) {
  if (isLive) return live.getKpiOperations()
  return sample.kpiOperations
}

export async function getNegotiationStats(isLive: boolean) {
  if (isLive) return live.getNegotiationStats()
  return sample.negotiationStats
}

export async function getSafetyLog(isLive: boolean) {
  if (isLive) return live.getSafetyLog()
  return sample.safetyLog
}

export async function getJobTypeVolume(isLive: boolean) {
  if (isLive) return live.getJobTypeVolume()
  return sample.jobTypeVolume
}

// ── Settings (always from sample — not stored in Supabase yet) ────────────────

export async function getSettings() {
  return sample.defaultSettings
}
