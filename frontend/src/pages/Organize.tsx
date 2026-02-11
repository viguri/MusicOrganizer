import { useState } from "react"
import { FolderSync, Play, RotateCcw, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import ProgressBar from "@/components/ProgressBar"
import TaskStatus from "@/components/TaskStatus"
import { useTaskStore } from "@/stores/taskStore"
import {
  planOrganize,
  executePlan,
  rollbackMoves,
  createFolders,
  cleanupEmpty,
  getTaskStatus,
  getOrganizeTaskStatus,
} from "@/lib/api"

interface MoveItem {
  source: string
  dest: string
  folder: string
  genre_raw: string
  strategy: string
  file_name: string
}

export default function Organize() {
  const [source, setSource] = useState("")
  const [dest, setDest] = useState("")
  const [planTaskId, setPlanTaskId] = useState<string | null>(null)
  const [execTaskId, setExecTaskId] = useState<string | null>(null)
  const [planResult, setPlanResult] = useState<Record<string, unknown> | null>(null)
  const [execResult, setExecResult] = useState<Record<string, unknown> | null>(null)
  const [rollbackLog, setRollbackLog] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const tasks = useTaskStore((s) => s.tasks)

  const pollTask = (taskId: string, getter: typeof getTaskStatus, onResult: (r: Record<string, unknown>) => void) => {
    const interval = setInterval(async () => {
      try {
        const status = await getter(taskId)
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

  const handlePlan = async () => {
    if (!source.trim() || !dest.trim()) return
    setLoading(true)
    setPlanResult(null)
    setExecResult(null)
    try {
      const res = await planOrganize(source.trim(), dest.trim())
      setPlanTaskId(res.task_id)
      pollTask(res.task_id, getTaskStatus, (result) => setPlanResult(result))
    } catch (e) {
      alert(String(e))
    } finally {
      setLoading(false)
    }
  }

  const handleExecute = async () => {
    if (!planResult?.plan_id) return
    setLoading(true)
    setExecResult(null)
    try {
      const res = await executePlan(String(planResult.plan_id))
      setExecTaskId(res.task_id)
      pollTask(res.task_id, getOrganizeTaskStatus, (result) => {
        setExecResult(result)
        if (result.rollback_log) setRollbackLog(String(result.rollback_log))
      })
    } catch (e) {
      alert(String(e))
    } finally {
      setLoading(false)
    }
  }

  const handleRollback = async () => {
    if (!rollbackLog) return
    if (!confirm("Are you sure you want to rollback all moves?")) return
    try {
      await rollbackMoves(rollbackLog)
      alert("Rollback completed")
    } catch (e) {
      alert(String(e))
    }
  }

  const handleCreateFolders = async () => {
    if (!dest.trim()) return
    try {
      const res = await createFolders(dest.trim())
      alert(`Created folder structure (${res.folders_in_mapping} folders in mapping)`)
    } catch (e) {
      alert(String(e))
    }
  }

  const handleCleanup = async () => {
    if (!dest.trim()) return
    try {
      const res = await cleanupEmpty(dest.trim())
      alert(`Removed ${res.removed.length} empty folders`)
    } catch (e) {
      alert(String(e))
    }
  }

  const planTask = planTaskId ? tasks[planTaskId] : undefined
  const moves = (planResult?.moves ?? []) as MoveItem[]
  const folderSummary = (planResult?.folder_summary ?? {}) as Record<string, number>

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Organize</h2>
        <p className="text-muted-foreground">Plan and execute file organization with dry-run preview</p>
      </div>

      {/* Paths */}
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Source Directory</label>
              <Input
                placeholder="e.g. G:\__DJ-ING\__NEW_RELEASES"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                className="font-mono text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Destination (Styles)</label>
              <Input
                placeholder="e.g. G:\__DJ-ING\_______MASTER_COLLECTION\_STYLES"
                value={dest}
                onChange={(e) => setDest(e.target.value)}
                className="font-mono text-sm"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <Button onClick={handlePlan} disabled={loading || !source.trim() || !dest.trim() || planTask?.status === "running"}>
              <FolderSync className="h-4 w-4" />
              Dry Run (Plan)
            </Button>
            <Button variant="outline" onClick={handleCreateFolders} disabled={!dest.trim()}>
              Create Folders
            </Button>
            <Button variant="outline" onClick={handleCleanup} disabled={!dest.trim()}>
              <Trash2 className="h-4 w-4" />
              Cleanup Empty
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Progress */}
      {(planTaskId || execTaskId) && (
        <Card>
          <CardContent className="p-4 space-y-3">
            {planTaskId && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-sm font-medium">Plan</span>
                  <TaskStatus taskId={planTaskId} />
                </div>
                <ProgressBar taskId={planTaskId} />
              </div>
            )}
            {execTaskId && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-sm font-medium">Execute</span>
                  <TaskStatus taskId={execTaskId} />
                </div>
                <ProgressBar taskId={execTaskId} />
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Plan Result */}
      {planResult && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Plan Summary</CardTitle>
              <div className="flex gap-2">
                <Button onClick={handleExecute} disabled={loading || !!execResult}>
                  <Play className="h-4 w-4" />
                  Execute Moves
                </Button>
                {rollbackLog && (
                  <Button variant="destructive" onClick={handleRollback}>
                    <RotateCcw className="h-4 w-4" />
                    Rollback
                  </Button>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Total Files</p>
                <p className="text-xl font-bold">{String(planResult.total_files)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">To Move</p>
                <p className="text-xl font-bold text-blue-600">{String(planResult.files_to_move)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Already Correct</p>
                <p className="text-xl font-bold text-green-600">{String(planResult.files_already_correct)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Unclassified</p>
                <p className="text-xl font-bold text-amber-600">{String(planResult.files_unclassified)}</p>
              </div>
            </div>

            {/* Folder Summary */}
            {Object.keys(folderSummary).length > 0 && (
              <div>
                <p className="text-sm font-medium mb-2">By Destination Folder</p>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-1 max-h-48 overflow-y-auto">
                  {Object.entries(folderSummary)
                    .sort(([, a], [, b]) => b - a)
                    .map(([folder, count]) => (
                      <div key={folder} className="flex justify-between text-sm px-2 py-1 bg-muted/50 rounded">
                        <span className="truncate">{folder}</span>
                        <span className="text-muted-foreground ml-2">{count}</span>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* Moves Table */}
            {moves.length > 0 && (
              <div>
                <p className="text-sm font-medium mb-2">Moves Preview (first {Math.min(moves.length, 100)})</p>
                <div className="border rounded-md overflow-auto max-h-96">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 sticky top-0">
                      <tr>
                        <th className="text-left p-2 font-medium">File</th>
                        <th className="text-left p-2 font-medium">Folder</th>
                        <th className="text-left p-2 font-medium">Genre</th>
                        <th className="text-left p-2 font-medium">Strategy</th>
                      </tr>
                    </thead>
                    <tbody>
                      {moves.slice(0, 100).map((m, i) => (
                        <tr key={i} className="border-t hover:bg-muted/30">
                          <td className="p-2 font-mono text-xs truncate max-w-xs">{m.file_name}</td>
                          <td className="p-2 text-xs">{m.folder}</td>
                          <td className="p-2 text-xs truncate max-w-32">{m.genre_raw || "—"}</td>
                          <td className="p-2 text-xs">{m.strategy}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Execution Result */}
      {execResult && (
        <Card className="border-green-500/50">
          <CardHeader>
            <CardTitle className="text-base text-green-600">Execution Complete</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Moved</p>
                <p className="text-xl font-bold text-green-600">{String(execResult.files_moved)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Failed</p>
                <p className="text-xl font-bold text-red-600">{String(execResult.files_failed)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Already Correct</p>
                <p className="text-xl font-bold">{String(execResult.files_already_correct)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
