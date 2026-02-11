import { useEffect, useState } from "react"
import { Music, FolderOpen, AlertTriangle, Hash, BarChart3, Tag } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import StatCard from "@/components/StatCard"
import { getSummary, getGenreStats, getConfig } from "@/lib/api"

interface Summary {
  total_tracks: number
  with_genre: number
  without_genre: number
  total_size_mb: number
  unique_genres: number
  unique_artists: number
  unique_labels: number
  by_extension: Record<string, number>
}

interface GenreStat {
  genre: string
  count: number
}

export default function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [genres, setGenres] = useState<GenreStat[]>([])
  const [config, setConfig] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      getSummary().catch(() => null),
      getGenreStats().catch(() => []),
      getConfig().catch(() => null),
    ]).then(([s, g, c]) => {
      if (s) setSummary(s as unknown as Summary)
      if (Array.isArray(g)) setGenres(g as GenreStat[])
      else if (g && typeof g === "object") {
        const arr = Object.entries(g as Record<string, number>).map(([genre, count]) => ({ genre, count }))
        arr.sort((a, b) => b.count - a.count)
        setGenres(arr)
      }
      if (c) setConfig(c as Record<string, unknown>)
    }).catch((e) => setError(String(e)))
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Dashboard</h2>
        <p className="text-muted-foreground">Overview of your music collection</p>
      </div>

      {error && (
        <Card className="border-destructive">
          <CardContent className="p-4 text-sm text-destructive">
            Backend not reachable. Start the server with <code className="bg-muted px-1 rounded">python -m backend.main</code>
          </CardContent>
        </Card>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Tracks"
          value={summary?.total_tracks ?? "—"}
          icon={Music}
          description="In database"
        />
        <StatCard
          title="With Genre"
          value={summary?.with_genre ?? "—"}
          icon={Tag}
          description={summary ? `${Math.round(((summary.with_genre) / (summary.total_tracks || 1)) * 100)}% classified` : undefined}
        />
        <StatCard
          title="Without Genre"
          value={summary?.without_genre ?? "—"}
          icon={AlertTriangle}
          description="Need classification"
        />
        <StatCard
          title="Unique Genres"
          value={summary?.unique_genres ?? "—"}
          icon={Hash}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Genres */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <BarChart3 className="h-4 w-4" />
              Top Genres
            </CardTitle>
          </CardHeader>
          <CardContent>
            {genres.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No genre data yet. Run a scan first.
              </p>
            ) : (
              <div className="space-y-2">
                {genres.slice(0, 15).map((g) => {
                  const maxCount = genres[0]?.count || 1
                  const pct = Math.round((g.count / maxCount) * 100)
                  return (
                    <div key={g.genre} className="flex items-center gap-3">
                      <span className="text-sm w-40 truncate" title={g.genre}>
                        {g.genre}
                      </span>
                      <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary rounded-full transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-xs text-muted-foreground w-10 text-right">
                        {g.count}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Collection Info */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FolderOpen className="h-4 w-4" />
              Collection Paths
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {config ? (
              <>
                <div>
                  <p className="text-xs text-muted-foreground">Master Collection</p>
                  <p className="text-sm font-mono truncate">{String(config.master_collection)}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Styles Directory</p>
                  <p className="text-sm font-mono truncate">{String(config.styles_dir)}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">New Releases</p>
                  <p className="text-sm font-mono truncate">{String(config.new_releases_dir)}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Target Folder Count</p>
                  <p className="text-sm font-bold">{String(config.target_folder_count)}</p>
                </div>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Loading configuration...</p>
            )}

            {summary?.by_extension && Object.keys(summary.by_extension).length > 0 && (
              <div className="pt-3 border-t">
                <p className="text-xs text-muted-foreground mb-2">File Types</p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(summary.by_extension).map(([ext, count]) => (
                    <span
                      key={ext}
                      className="inline-flex items-center gap-1 px-2 py-0.5 bg-muted rounded text-xs"
                    >
                      {ext} <span className="font-medium">{count}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
