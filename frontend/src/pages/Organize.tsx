import { useEffect, useState } from "react"
import { FolderSync, Play, RotateCcw, Trash2, FolderTree, Folder, AlertTriangle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import FolderPicker from "@/components/FolderPicker"
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
  updatePlanFolders,
} from "@/lib/api"

interface MoveItem {
  source: string
  dest: string
  folder: string
  genre_raw: string
  strategy: string
  file_name: string
}

interface DuplicateItem {
  source: string
  existing: string
  file_name: string
  method: string
  detail: string
}

export default function Organize() {
  const [source, setSource] = useState("")
  const [dest, setDest] = useState("")
  const [recursive, setRecursive] = useState(true)
  const [planTaskId, setPlanTaskId] = useState<string | null>(null)
  const [execTaskId, setExecTaskId] = useState<string | null>(null)
  const [planResult, setPlanResult] = useState<Record<string, unknown> | null>(null)
  const [execResult, setExecResult] = useState<Record<string, unknown> | null>(null)
  const [rollbackLog, setRollbackLog] = useState<string | null>(null)
  const [folderOverrides, setFolderOverrides] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const tasks = useTaskStore((s) => s.tasks)

  useEffect(() => {
    if (!planResult) {
      setFolderOverrides({})
      return
    }
    const summary = (planResult.folder_summary ?? {}) as Record<string, number>
    const initialOverrides: Record<string, string> = {}
    Object.keys(summary).forEach((folder) => {
      initialOverrides[folder] = folder
    })
    setFolderOverrides(initialOverrides)
  }, [planResult])

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

  const handleApplyFolderOverrides = async () => {
    if (!planResult?.plan_id) return

    const overrides = Object.fromEntries(
      Object.entries(folderOverrides)
        .map(([original, target]) => [original, target.trim()])
        .filter(([original, target]) => target && target !== original)
    ) as Record<string, string>

    if (Object.keys(overrides).length === 0) {
      alert("No folder name changes to apply")
      return
    }

    setLoading(true)
    try {
      const res = await updatePlanFolders(String(planResult.plan_id), overrides)
      setPlanResult(res.result)
      setExecResult(null)
      setRollbackLog(null)
    } catch (e) {
      alert(String(e))
    } finally {
      setLoading(false)
    }
  }

  const handlePlan = async () => {
    if (!source.trim() || !dest.trim()) return
    setLoading(true)
    setPlanResult(null)
    setExecResult(null)
    try {
      const res = await planOrganize(source.trim(), dest.trim(), recursive)
      setPlanTaskId(res.task_id)
      pollTask(res.task_id, getOrganizeTaskStatus, (result) => setPlanResult(result))
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
  const duplicates = (planResult?.duplicates ?? []) as DuplicateItem[]
  const folderSummary = (planResult?.folder_summary ?? {}) as Record<string, number>
  const hasFolderChanges = Object.entries(folderOverrides).some(
    ([original, target]) => target.trim() !== "" && target.trim() !== original
  )

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
            <FolderPicker
              value={source}
              onChange={setSource}
              placeholder="e.g. G:\__DJ-ING\__NEW_RELEASES"
              label="Source Directory"
            />
            <FolderPicker
              value={dest}
              onChange={setDest}
              placeholder="e.g. G:\__DJ-ING\_______MASTER_COLLECTION\_STYLES"
              label="Destination (Styles)"
            />
          </div>
          <label className="flex items-center gap-2 text-sm cursor-pointer select-none w-fit">
            <input
              type="checkbox"
              checked={recursive}
              onChange={(e) => setRecursive(e.target.checked)}
              className="rounded border-input"
            />
            {recursive ? <FolderTree className="h-4 w-4 text-muted-foreground" /> : <Folder className="h-4 w-4 text-muted-foreground" />}
            <span>Include subdirectories in source</span>
            <span className="text-xs text-muted-foreground">
              {recursive ? "(scans all subfolders)" : "(only top-level files)"}
            </span>
          </label>
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
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
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
              <div>
                <p className="text-xs text-muted-foreground">Duplicates Skipped</p>
                <p className="text-xl font-bold text-orange-600">{String(planResult.duplicates_skipped ?? 0)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Dry Run Time</p>
                <p className="text-xl font-bold text-violet-600">
                  {Number(planResult.elapsed_seconds ?? 0).toFixed(2)}s
                </p>
              </div>
            </div>

            {/* Folder Summary */}
            {Object.keys(folderSummary).length > 0 && (
              <div>
                <div className="flex items-center justify-between gap-3 mb-2">
                  <p className="text-sm font-medium">By Destination Folder (editable)</p>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleApplyFolderOverrides}
                    disabled={loading || !hasFolderChanges}
                  >
                    Apply Folder Changes
                  </Button>
                </div>
                <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                  {Object.entries(folderSummary)
                    .sort(([, a], [, b]) => b - a)
                    .map(([folder, count]) => (
                      <div key={folder} className="grid grid-cols-12 gap-2 items-center text-sm">
                        <span className="col-span-4 md:col-span-3 truncate text-muted-foreground" title={folder}>
                          {folder}
                        </span>
                        <input
                          className="col-span-6 md:col-span-7 rounded border border-input bg-background px-2 py-1 text-xs"
                          value={folderOverrides[folder] ?? folder}
                          onChange={(e) =>
                            setFolderOverrides((prev) => ({
                              ...prev,
                              [folder]: e.target.value,
                            }))
                          }
                          placeholder="Folder or subfolder path (e.g. Techno/Peak Time)"
                        />
                        <span className="col-span-2 text-right text-muted-foreground">{count}</span>
                      </div>
                    ))}
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  Use "/" to create subfolders (example: "House/Afro House"). Invalid characters are sanitized automatically.
                </p>
              </div>
            )}

            {/* Duplicates Table */}
            {duplicates.length > 0 && (
              <div>
                <p className="text-sm font-medium mb-2 flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-orange-500" />
                  Duplicates Detected ({duplicates.length})
                </p>
                <div className="border rounded-md overflow-auto max-h-64 border-orange-500/30">
                  <table className="w-full text-sm">
                    <thead className="bg-orange-500/10 sticky top-0">
                      <tr>
                        <th className="text-left p-2 font-medium">Source File</th>
                        <th className="text-left p-2 font-medium">Existing In Dest</th>
                        <th className="text-left p-2 font-medium">Method</th>
                        <th className="text-left p-2 font-medium">Detail</th>
                      </tr>
                    </thead>
                    <tbody>
                      {duplicates.slice(0, 100).map((d, i) => (
                        <tr key={i} className="border-t hover:bg-muted/30">
                          <td className="p-2 font-mono text-xs truncate max-w-48">{d.file_name}</td>
                          <td className="p-2 font-mono text-xs truncate max-w-48">{d.existing.split(/[\\/]/).pop()}</td>
                          <td className="p-2 text-xs">
                            <Badge variant={d.method === "hash" ? "destructive" : d.method === "name_size" ? "secondary" : "outline"} className="text-[10px]">
                              {d.method === "name_size" ? "Name+Size" : d.method === "hash" ? "SHA-256" : "Metadata"}
                            </Badge>
                          </td>
                          <td className="p-2 text-xs truncate max-w-64 text-muted-foreground">{d.detail}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {duplicates.length > 100 && (
                  <p className="text-xs text-muted-foreground mt-1">Showing first 100 of {duplicates.length} duplicates</p>
                )}
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
