import { NavLink, Outlet } from "react-router-dom"
import {
  LayoutDashboard,
  ScanSearch,
  FolderSync,
  FileText,
  Copy,
  Settings,
  Wifi,
  WifiOff,
  Sun,
  Moon,
  Monitor,
} from "lucide-react"
import { useWebSocket } from "@/hooks/useWebSocket"
import { useTheme } from "@/hooks/useTheme"
import { useTaskStore } from "@/stores/taskStore"
import { useEffect } from "react"

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/scan", icon: ScanSearch, label: "Scan & Classify" },
  { to: "/organize", icon: FolderSync, label: "Organize" },
  { to: "/clean-names", icon: FileText, label: "Name Cleaner" },
  { to: "/duplicates", icon: Copy, label: "Duplicates" },
  { to: "/settings", icon: Settings, label: "Settings" },
]

const themeIcons = { light: Sun, dark: Moon, system: Monitor } as const
const themeLabels = { light: "Light", dark: "Dark", system: "System" } as const

export default function Layout() {
  const { connected, lastMessage } = useWebSocket()
  const { theme, toggle } = useTheme()
  const updateFromWs = useTaskStore((s) => s.updateFromWs)

  useEffect(() => {
    if (lastMessage) updateFromWs(lastMessage)
  }, [lastMessage, updateFromWs])

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="w-60 border-r bg-sidebar-background flex flex-col">
        <div className="p-4 border-b">
          <h1 className="text-lg font-bold text-sidebar-foreground">Music Organizer</h1>
          <p className="text-xs text-muted-foreground mt-0.5">DJ Collection Manager</p>
        </div>

        <nav className="flex-1 p-2 space-y-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                    : "text-sidebar-foreground hover:bg-sidebar-accent/50"
                }`
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t space-y-2">
          <button
            onClick={toggle}
            className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors w-full px-1 py-1 rounded"
            title={`Theme: ${themeLabels[theme]}`}
          >
            {(() => { const Icon = themeIcons[theme]; return <Icon className="h-3.5 w-3.5" />; })()}
            <span>{themeLabels[theme]}</span>
          </button>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {connected ? (
              <>
                <Wifi className="h-3 w-3 text-green-500" />
                <span>Connected</span>
              </>
            ) : (
              <>
                <WifiOff className="h-3 w-3 text-red-500" />
                <span>Disconnected</span>
              </>
            )}
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-6 max-w-7xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
