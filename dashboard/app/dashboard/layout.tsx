"use client"

import { useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  LayoutDashboard,
  Users,
  Wrench,
  Settings,
  ChevronLeft,
  ChevronRight,
  Zap,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Toaster } from "sonner"
import { DataSourceProvider, useDataSource } from "@/lib/data-context"
import { Database, TestTube2 } from "lucide-react"

const navItems = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/dashboard/customers", label: "Customers", icon: Users },
  { href: "/dashboard/operations", label: "Operations", icon: Wrench },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
]

function DataSourceToggle({ collapsed }: { collapsed: boolean }) {
  const { dataSource, setDataSource } = useDataSource()
  const isLive = dataSource === "live"

  return (
    <div className={cn("p-3 border-t border-border", collapsed && "flex justify-center")}>
      <button
        onClick={() => setDataSource(isLive ? "sample" : "live")}
        className={cn(
          "flex items-center gap-3 w-full rounded-md px-3 py-2.5 text-sm font-medium transition-colors",
          collapsed && "justify-center px-0 w-auto",
          isLive
            ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
            : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
        )}
        title={collapsed ? (isLive ? "Live Data" : "Demo Data") : undefined}
      >
        {isLive ? <Database className="w-4 h-4 shrink-0" /> : <TestTube2 className="w-4 h-4 shrink-0" />}
        {!collapsed && <span>{isLive ? "Live Data" : "Demo Data"}</span>}
      </button>
    </div>
  )
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false)
  const pathname = usePathname()

  return (
    <DataSourceProvider>
      <div className="flex h-screen bg-background overflow-hidden">
      {/* Sidebar */}
      <aside
        className={cn(
          "flex flex-col border-r border-border bg-card transition-all duration-300 shrink-0",
          collapsed ? "w-16" : "w-60"
        )}
      >
        {/* Logo */}
        <div className={cn("flex items-center gap-3 px-4 py-5 border-b border-border", collapsed && "justify-center px-0")}>
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary shrink-0">
            <Zap className="w-4 h-4 text-primary-foreground" />
          </div>
          {!collapsed && (
            <div className="flex flex-col">
              <span className="font-semibold text-sm text-foreground leading-tight">FixFlow</span>
              <span className="text-[10px] text-muted-foreground leading-tight">Business Dashboard</span>
            </div>
          )}
        </div>

        {/* Nav items */}
        <nav className="flex flex-col gap-1 p-3 flex-1">
          {navItems.map(({ href, label, icon: Icon }) => {
            const active = pathname === href
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors",
                  collapsed && "justify-center px-0",
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                )}
                title={collapsed ? label : undefined}
              >
                <Icon className="w-4 h-4 shrink-0" />
                {!collapsed && <span>{label}</span>}
              </Link>
            )
          })}
        </nav>

        {/* Data source toggle */}
        <DataSourceToggle collapsed={collapsed} />

        {/* Collapse toggle */}
        <div className="p-3 border-t border-border">
          <button
            onClick={() => setCollapsed(!collapsed)}
            className={cn(
              "flex items-center gap-3 w-full rounded-md px-3 py-2.5 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors",
              collapsed && "justify-center px-0"
            )}
          >
            {collapsed ? <ChevronRight className="w-4 h-4 shrink-0" /> : <ChevronLeft className="w-4 h-4 shrink-0" />}
            {!collapsed && <span>Collapse</span>}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>

      <Toaster richColors position="top-right" />
    </div>
    </DataSourceProvider>
  )
}
