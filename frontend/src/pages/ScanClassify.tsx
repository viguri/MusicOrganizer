import { useState } from "react"
import { ScanSearch, Play, BarChart3, FolderTree, Folder } from "lucide-react"
import { Button } from "@/components/ui/button"
import FolderPicker from "@/components/FolderPicker"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import ProgressBar from "@/components/ProgressBar"
import TaskStatus from "@/components/TaskStatus"
import { useTaskStore } from "@/stores/taskStore"
import { startScan, analyzeGenres, getTaskStatus } from "@/lib/api"

function TopGenresList({ genres }: { genres: Record<string, number> }) {
  return (
    <div>
      <p className="text-sm font-medium mb-2">Top Genres</p>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-1 max-h-64 overflow-y-auto">
        {Object.entries(genres)
          .sort(([, a], [, b]) => b - a)
          .map(([genre, count]) => (
            <div key={genre} className="flex justify-between text-sm px-2 py-1 bg-muted/50 rounded">
              <span className="truncate">{genre}</span>
              <span className="text-muted-foreground ml-2">{count}</span>
            </div>
          ))}
      </div>
    </div>
  )
}

export default function ScanClassify() {
  const [directory, setDirectory] = useState("")
  const [recursive, setRecursive] = useState(true)
  const [scanTaskId, setScanTaskId] = useState<string | null>(null)
  const [analyzeTaskId, setAnalyzeTaskId] = useState<string | null>(null)
  const [scanResult, setScanResult] = useState<Record<string, unknown> | null>(null)
  const [analyzeResult, setAnalyzeResult] = useState<Record<string, unknown> | null>(null)
  const [tab, setTab] = useState("scan")
  const [loading, setLoading] = useState(false)
  const tasks = useTaskStore((s) => s.tasks)

  const handleScan = async () => {
    if (!directory.trim()) return
    setLoading(true)
    setScanResult(null)
    try {
      const res = await startScan(directory.trim(), true, recursive)
      setScanTaskId(res.task_id)
      pollTask(res.task_id, (result) => setScanResult(result))
    } catch (e) {
      alert(String(e))
    } finally {
      setLoading(false)
    }
  }

  const handleAnalyze = async () => {
    if (!directory.trim()) return
    setLoading(true)
    setAnalyzeResult(null)
    try {
      const res = await analyzeGenres(directory.trim(), true, 50, recursive)
      setAnalyzeTaskId(res.task_id)
      pollTask(res.task_id, (result) => setAnalyzeResult(result))
    } catch (e) {
      alert(String(e))
    } finally {
      setLoading(false)
    }
  }

  const pollTask = (taskId: string, onResult: (r: Record<string, unknown>) => void) => {
    const interval = setInterval(async () => {
      try {
        const status = await getTaskStatus(taskId)
        if (status.status === "completed") {
          clearInterval(interval)
          if (status.result) onResult(status.result)
        } else if (status.status === "error") {
          clearInterval(interval)
          alert(status.error || "Task failed")
        }
      } catch {
        clearInterval(interval)
      }
    }, 2000)
  }

  const scanTask = scanTaskId ? tasks[scanTaskId] : undefined
  const analyzeTask = analyzeTaskId ? tasks[analyzeTaskId] : undefined

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Scan & Classify</h2>
        <p className="text-muted-foreground">Scan directories for audio files and analyze genres</p>
      </div>

      {/* Directory Input */}
      <Card>
        <CardContent className="p-4 space-y-3">
          <FolderPicker
            value={directory}
            onChange={setDirectory}
            placeholder="Directory path (e.g. G:\__DJ-ING\_______MASTER_COLLECTION)"
          />
          <label className="flex items-center gap-2 text-sm cursor-pointer select-none w-fit">
            <input
              type="checkbox"
              checked={recursive}
              onChange={(e) => setRecursive(e.target.checked)}
              className="rounded border-input"
            />
            {recursive ? <FolderTree className="h-4 w-4 text-muted-foreground" /> : <Folder className="h-4 w-4 text-muted-foreground" />}
            <span>Include subdirectories</span>
            <span className="text-xs text-muted-foreground">
              {recursive ? "(scans all subfolders recursively)" : "(only files in the selected folder)"}
            </span>
          </label>
        </CardContent>
      </Card>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="scan">
            <ScanSearch className="h-4 w-4 mr-1" /> Scan Files
          </TabsTrigger>
          <TabsTrigger value="analyze">
            <BarChart3 className="h-4 w-4 mr-1" /> Analyze Genres
          </TabsTrigger>
        </TabsList>

        {/* Scan Tab */}
        <TabsContent value="scan">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Scan Directory</CardTitle>
                <div className="flex items-center gap-2">
                  <TaskStatus taskId={scanTaskId} />
                  <Button onClick={handleScan} disabled={loading || !directory.trim() || scanTask?.status === "running"}>
                    <Play className="h-4 w-4" />
                    Start Scan
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Scans the directory for audio files (MP3, FLAC, WAV, M4A, AIFF) and reads ID3 metadata.
                Results are saved to the local database.
              </p>

              <ProgressBar taskId={scanTaskId} />

              {scanResult && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t">
                  <div>
                    <p className="text-xs text-muted-foreground">Total Files</p>
                    <p className="text-xl font-bold">{String(scanResult.total_files)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">With Genre</p>
                    <p className="text-xl font-bold text-green-600">{String(scanResult.with_genre)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Without Genre</p>
                    <p className="text-xl font-bold text-amber-600">{String(scanResult.without_genre)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Errors</p>
                    <p className="text-xl font-bold text-red-600">{String(scanResult.errors)}</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Analyze Tab */}
        <TabsContent value="analyze">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Analyze Genres</CardTitle>
                <div className="flex items-center gap-2">
                  <TaskStatus taskId={analyzeTaskId} />
                  <Button onClick={handleAnalyze} disabled={loading || !directory.trim() || analyzeTask?.status === "running"}>
                    <BarChart3 className="h-4 w-4" />
                    Analyze
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Scans all files, counts genre frequencies, groups similar genres using AI embeddings,
                and generates a folder_mapping.json with ~50 proposed style folders.
              </p>

              <ProgressBar taskId={analyzeTaskId} />

              {analyzeResult && (
                <div className="space-y-4 pt-4 border-t">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <p className="text-xs text-muted-foreground">Total Tracks</p>
                      <p className="text-xl font-bold">{String(analyzeResult.total_tracks)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Unique Genres</p>
                      <p className="text-xl font-bold">{String(analyzeResult.unique_genres)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Proposed Folders</p>
                      <p className="text-xl font-bold text-green-600">{String(analyzeResult.proposed_folders)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Labels Mapped</p>
                      <p className="text-xl font-bold">{String(analyzeResult.labels_mapped)}</p>
                    </div>
                  </div>

                  {analyzeResult.top_genres != null && typeof analyzeResult.top_genres === "object" && (
                    <TopGenresList genres={analyzeResult.top_genres as Record<string, number>} />
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
