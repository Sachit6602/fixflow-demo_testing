"use client"

import { createContext, useContext, useState, ReactNode } from "react"

type DataSource = "sample" | "live"

interface DataSourceContextType {
  dataSource: DataSource
  setDataSource: (source: DataSource) => void
  isLive: boolean
}

const DataSourceContext = createContext<DataSourceContextType>({
  dataSource: "sample",
  setDataSource: () => {},
  isLive: false,
})

export function DataSourceProvider({ children }: { children: ReactNode }) {
  const [dataSource, setDataSource] = useState<DataSource>("sample")

  return (
    <DataSourceContext.Provider value={{ dataSource, setDataSource, isLive: dataSource === "live" }}>
      {children}
    </DataSourceContext.Provider>
  )
}

export function useDataSource() {
  return useContext(DataSourceContext)
}
