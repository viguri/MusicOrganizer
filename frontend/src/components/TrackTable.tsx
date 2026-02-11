import { Badge } from "@/components/ui/badge"

export interface Track {
  file_path: string
  file_name: string
  artist?: string
  title?: string
  genre_raw?: string
  genre_normalized?: string
  label?: string
  bpm?: number
  key?: string
  duration?: number
  status?: string
  source_folder?: string
  dest_folder?: string
}

interface TrackTableProps {
  tracks: Track[]
  maxRows?: number
  showDestination?: boolean
}

export default function TrackTable({ tracks, maxRows = 100, showDestination = false }: TrackTableProps) {
  if (tracks.length === 0) {
    return <p className="text-sm text-muted-foreground py-4">No tracks to display.</p>
  }

  const displayed = tracks.slice(0, maxRows)

  return (
    <div className="border rounded-md overflow-auto max-h-[500px]">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 sticky top-0">
          <tr>
            <th className="text-left p-2 font-medium">File</th>
            <th className="text-left p-2 font-medium">Artist</th>
            <th className="text-left p-2 font-medium">Title</th>
            <th className="text-left p-2 font-medium">Genre</th>
            <th className="text-left p-2 font-medium">BPM</th>
            <th className="text-left p-2 font-medium">Key</th>
            {showDestination && <th className="text-left p-2 font-medium">Dest</th>}
            <th className="text-left p-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {displayed.map((t, i) => (
            <tr key={i} className="border-t hover:bg-muted/30">
              <td className="p-2 font-mono text-xs truncate max-w-48" title={t.file_path}>
                {t.file_name}
              </td>
              <td className="p-2 text-xs truncate max-w-32">{t.artist || "—"}</td>
              <td className="p-2 text-xs truncate max-w-32">{t.title || "—"}</td>
              <td className="p-2 text-xs truncate max-w-28">{t.genre_raw || t.genre_normalized || "—"}</td>
              <td className="p-2 text-xs">{t.bpm || "—"}</td>
              <td className="p-2 text-xs">{t.key || "—"}</td>
              {showDestination && (
                <td className="p-2 text-xs truncate max-w-32">{t.dest_folder || "—"}</td>
              )}
              <td className="p-2">
                {t.status && (
                  <Badge
                    variant={
                      t.status === "scanned" ? "secondary" :
                      t.status === "moved" ? "default" :
                      t.status === "error" ? "destructive" : "outline"
                    }
                    className="text-[10px] px-1.5 py-0"
                  >
                    {t.status}
                  </Badge>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {tracks.length > maxRows && (
        <div className="p-2 text-center text-xs text-muted-foreground border-t">
          Showing {maxRows} of {tracks.length} tracks
        </div>
      )}
    </div>
  )
}
