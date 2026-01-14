import { useState, useEffect } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'
import { getHealthStatus } from '@/api/health'

interface MainLayoutProps {
  children: React.ReactNode
}

export function MainLayout({ children }: MainLayoutProps) {
  const [isLiveMode, setIsLiveMode] = useState(false)

  useEffect(() => {
    // Check if we're in live SMS mode
    getHealthStatus()
      .then((status) => {
        setIsLiveMode(status.dry_run === false)
      })
      .catch(() => {
        // Ignore errors - assume dry run mode
      })
  }, [])

  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <div className="flex flex-col transition-all duration-300 ml-64">
        <Topbar />
        {isLiveMode && (
          <div className="bg-red-600 text-white px-4 py-2 flex items-center justify-center gap-2 text-sm font-medium">
            <AlertTriangle className="h-4 w-4" />
            <span>SMS IS LIVE — Messages will be sent to real phone numbers</span>
            <AlertTriangle className="h-4 w-4" />
          </div>
        )}
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  )
}

