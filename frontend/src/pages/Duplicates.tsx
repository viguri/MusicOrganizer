import { useState, useEffect } from "react"
import { Copy, Play, Trash2, AlertTriangle, CheckCircle, History, RefreshCw, FolderInput } from "lucide-react"
import { Button } from "@/components/ui/button"
import FolderPicker from "@/components/FolderPicker"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import ProgressBar from "@/components/ProgressBar"
import TaskStatus from "@/components/TaskStatus"
import { useTaskStore } from "@/stores/taskStore"
import { 
  scanDuplicates, 
  getOrganizeTaskStatus, 
  deleteDuplicates,
  moveDuplicates, 
  listDuplicateScans,
  getDuplicateScan 
} from "@/lib/api"

interface FileInfo {
  path: string
  action: "keep" | "delete"
  reason: string
}

interface DupeGroup {
  hash?: string
  key?: string
  files: string[]
  files_info?: FileInfo[]
}

interface DeleteResult {
  dry_run: boolean
  total_to_delete: number
  total_deleted: number
  total_errors: number
  files_to_delete: Array<{ path: string; reason: string; type: string }>
  errors: Array<{ path: string; reason: string; type: string; error: string }>
}

interface MoveResult {
  dry_run: boolean
  total_to_move: number
  total_moved: number
  total_errors: number
  files_to_move: Array<{ path: string; reason: string; type: string; destination?: string }>
  errors: Array<{ path: string; reason: string; type: string; error: string }>
  destination_folder: string | null
}

interface ScanRecord {
  id: string
  source_dir: string
  against_dir: string | null
  total_hash_groups: number
  total_hash_files: number
  total_meta_groups: number
  total_meta_files: number
  created_at: string
}

interface DupeResult {
  total_hash_groups: number
  total_hash_files: number
  total_meta_groups: number
  total_meta_files: number
  hash_duplicates: DupeGroup[]
  metadata_duplicates: DupeGroup[]
}

export default function Duplicates() {
  const [source, setSource] = useState("")
  const [against, setAgainst] = useState("")
  const [taskId, setTaskId] = useState<string | null>(null)
  const [result, setResult] = useState<DupeResult | null>(null)
  const [tab, setTab] = useState("hash")
  const [loading, setLoading] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteResult, setDeleteResult] = useState<DeleteResult | null>(null)
  const [moveResult, setMoveResult] = useState<MoveResult | null>(null)
  const [moveDestination, setMoveDestination] = useState("")
  const [preserveStructure, setPreserveStructure] = useState(true)
  const [showMoveOptions, setShowMoveOptions] = useState(false)
  const [previousScans, setPreviousScans] = useState<ScanRecord[]>([])
  const [showPreviousScans, setShowPreviousScans] = useState(false)
  const tasks = useTaskStore((s) => s.tasks)

  useEffect(() => {
    loadPreviousScans()
  }, [])

  const loadPreviousScans = async () => {
    try {
      const data = await listDuplicateScans(10)
      setPreviousScans(data.scans)
    } catch (e) {
      console.error("Failed to load previous scans:", e)
    }
  }

  const loadScan = async (scanId: string) => {
    try {
      setLoading(true)
      const data = await getDuplicateScan(scanId)
      setResult(data as unknown as DupeResult)
      setTaskId(scanId)
      setDeleteResult(null)
      setShowPreviousScans(false)
    } catch (e) {
      alert(String(e))
    } finally {
      setLoading(false)
    }
  }

  const pollTask = (tid: string, onResult: (r: Record<string, unknown>) => void) => {
    const interval = setInterval(async () => {
      try {
        const status = await getOrganizeTaskStatus(tid)
        if (status.status === "completed") {
          clearInterval(interval)
          if (status.result) {
            onResult(status.result)
            loadPreviousScans()
          }
        } else if (status.status === "error") {
          clearInterval(interval)
          alert(status.error || "Task failed")
        }
      } catch {
        clearInterval(interval)
      }
    }, 2000)
  }

  const handleScan = async () => {
    if (!source.trim()) return
    setLoading(true)
    setResult(null)
    setDeleteResult(null)
    setMoveResult(null)
    try {
      const res = await scanDuplicates(source.trim(), against.trim() || undefined)
      setTaskId(res.task_id)
      pollTask(res.task_id, (r) => setResult(r as unknown as DupeResult))
    } catch (e) {
      alert(String(e))
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (dryRun: boolean) => {
    if (!taskId) return
    setDeleting(true)
    setDeleteResult(null)
    setMoveResult(null)
    try {
      const res = await deleteDuplicates(taskId, true, false, dryRun)
      setDeleteResult(res)
      if (!dryRun) {
        alert(`Successfully deleted ${res.total_deleted} duplicate files!`)
        setResult(null)
      }
    } catch (e) {
      alert(String(e))
    } finally {
      setDeleting(false)
    }
  }

  const handleMove = async (dryRun: boolean) => {
    console.log("handleMove called", { taskId, moveDestination, dryRun, preserveStructure })
    
    if (!taskId) {
      alert("No task ID found. Please scan for duplicates first.")
      return
    }
    
    if (!moveDestination.trim()) {
      alert("Please select a destination folder")
      return
    }
    
    setDeleting(true)
    setDeleteResult(null)
    setMoveResult(null)
    
    try {
      console.log("Calling moveDuplicates API...")
      const res = await moveDuplicates(taskId, moveDestination.trim(), true, false, dryRun, preserveStructure)
      console.log("Move result:", res)
      setMoveResult(res)
      
      if (!dryRun && res.total_moved > 0) {
        alert(`Successfully moved ${res.total_moved} duplicate files to ${res.destination_folder}!`)
        setResult(null)
      } else if (dryRun) {
        alert(`Preview: ${res.total_to_move} files would be moved to ${res.destination_folder || moveDestination}`)
      } else if (res.total_moved === 0) {
        alert("No files were moved. Check the results for details.")
      }
    } catch (e) {
      console.error("Move duplicates error:", e)
      alert(`Error: ${String(e)}`)
    } finally {
      setDeleting(false)
    }
  }

  const task = taskId ? tasks[taskId] : undefined

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Duplicates</h2>
        <p className="text-muted-foreground">
          Find duplicate files by SHA-256 hash and metadata comparison
        </p>
      </div>

      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <FolderPicker
              value={source}
              onChange={setSource}
              placeholder="Directory to scan for duplicates"
              label="Source Directory"
            />
            <FolderPicker
              value={against}
              onChange={setAgainst}
              placeholder="Second directory to compare against"
              label="Compare Against (optional)"
            />
          </div>
          <Button onClick={handleScan} disabled={loading || !source.trim() || task?.status === "running"}>
            <Play className="h-4 w-4" />
            Scan for Duplicates
          </Button>
        </CardContent>
      </Card>

      {taskId && (
        <Card>
          <CardContent className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Copy className="h-4 w-4" />
              <span className="text-sm font-medium">Progress</span>
              <TaskStatus taskId={taskId} />
            </div>
            <ProgressBar taskId={taskId} />
          </CardContent>
        </Card>
      )}

      {previousScans.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <History className="h-4 w-4" />
                Previous Scans
              </CardTitle>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowPreviousScans(!showPreviousScans)}
              >
                {showPreviousScans ? "Hide" : "Show"}
              </Button>
            </div>
          </CardHeader>
          {showPreviousScans && (
            <CardContent>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {previousScans.map((scan) => (
                  <div
                    key={scan.id}
                    className="flex items-center justify-between p-2 border rounded hover:bg-accent cursor-pointer"
                    onClick={() => loadScan(scan.id)}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-mono truncate">{scan.source_dir}</p>
                      <p className="text-xs text-muted-foreground">
                        {scan.total_hash_groups} groups, {scan.total_hash_files} duplicates
                      </p>
                    </div>
                    <RefreshCw className="h-4 w-4 text-muted-foreground" />
                  </div>
                ))}
              </div>
            </CardContent>
          )}
        </Card>
      )}

      {result && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Results</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-xs text-muted-foreground">Hash Groups</p>
                  <p className="text-xl font-bold">{result.total_hash_groups}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Hash Duplicate Files</p>
                  <p className="text-xl font-bold text-red-600">{result.total_hash_files}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Metadata Groups</p>
                  <p className="text-xl font-bold">{result.total_meta_groups}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Metadata Duplicate Files</p>
                  <p className="text-xl font-bold text-amber-600">{result.total_meta_files}</p>
                </div>
              </div>

              {result.total_hash_files > 0 && (
                <div className="space-y-3">
                  <div className="flex gap-2">
                    <Button
                      onClick={() => setShowMoveOptions(!showMoveOptions)}
                      variant="outline"
                    >
                      <FolderInput className="h-4 w-4" />
                      {showMoveOptions ? "Hide" : "Show"} Move Options
                    </Button>
                    <Button
                      onClick={() => handleDelete(true)}
                      disabled={deleting}
                      variant="outline"
                    >
                      <AlertTriangle className="h-4 w-4" />
                      Preview Deletion
                    </Button>
                    <Button
                      onClick={() => handleDelete(false)}
                      disabled={deleting}
                      variant="destructive"
                    >
                      <Trash2 className="h-4 w-4" />
                      Delete Duplicates
                    </Button>
                  </div>

                  {showMoveOptions && (
                    <Card>
                      <CardContent className="p-4 space-y-3">
                        <div className="space-y-2">
                          <label className="text-sm font-medium">Destination Folder</label>
                          <FolderPicker
                            value={moveDestination}
                            onChange={setMoveDestination}
                            placeholder="Select folder to move duplicates"
                          />
                        </div>
                        <div className="flex items-center space-x-2">
                          <input
                            type="checkbox"
                            id="preserve-structure"
                            checked={preserveStructure}
                            onChange={(e) => setPreserveStructure(e.target.checked)}
                            className="h-4 w-4"
                          />
                          <label htmlFor="preserve-structure" className="text-sm cursor-pointer">
                            Preserve directory structure
                          </label>
                        </div>
                        <div className="flex gap-2">
                          <Button
                            onClick={() => handleMove(true)}
                            disabled={deleting || !moveDestination.trim()}
                            variant="outline"
                          >
                            <AlertTriangle className="h-4 w-4" />
                            Preview Move
                          </Button>
                          <Button
                            onClick={() => handleMove(false)}
                            disabled={deleting || !moveDestination.trim()}
                          >
                            <FolderInput className="h-4 w-4" />
                            Move Duplicates
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </div>
              )}

              <Tabs value={tab} onValueChange={setTab}>
                <TabsList>
                  <TabsTrigger value="hash">Hash Duplicates ({result.hash_duplicates.length})</TabsTrigger>
                  <TabsTrigger value="meta">Metadata Duplicates ({result.metadata_duplicates.length})</TabsTrigger>
                </TabsList>

                <TabsContent value="hash">
                  {result.hash_duplicates.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-4">No exact duplicates found.</p>
                  ) : (
                    <div className="space-y-3 max-h-96 overflow-y-auto">
                      {result.hash_duplicates.map((group, i) => (
                        <div key={i} className="border rounded-md p-3">
                          <p className="text-xs text-muted-foreground mb-1">
                            Hash: {group.hash}... ({group.files.length} files)
                          </p>
                          <div className="space-y-1">
                            {group.files_info ? (
                              group.files_info.map((fileInfo, j) => (
                                <div key={j} className="flex items-center gap-2">
                                  {fileInfo.action === "keep" ? (
                                    <CheckCircle className="h-3 w-3 text-green-600 flex-shrink-0" />
                                  ) : (
                                    <Trash2 className="h-3 w-3 text-red-600 flex-shrink-0" />
                                  )}
                                  <p className="text-xs font-mono truncate flex-1">{fileInfo.path}</p>
                                  <Badge variant={fileInfo.action === "keep" ? "default" : "destructive"} className="text-xs">
                                    {fileInfo.action === "keep" ? "KEEP" : "DELETE"}
                                  </Badge>
                                </div>
                              ))
                            ) : (
                              group.files.map((f, j) => (
                                <p key={j} className="text-xs font-mono truncate">{f}</p>
                              ))
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="meta">
                  {result.metadata_duplicates.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-4">No metadata duplicates found.</p>
                  ) : (
                    <div className="space-y-3 max-h-96 overflow-y-auto">
                      {result.metadata_duplicates.map((group, i) => (
                        <div key={i} className="border rounded-md p-3">
                          <p className="text-xs text-muted-foreground mb-1">
                            {group.key} ({group.files.length} files)
                          </p>
                          <div className="space-y-1">
                            {group.files.map((f, j) => (
                              <p key={j} className="text-xs font-mono truncate">{f}</p>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>

          {deleteResult && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  {deleteResult.dry_run ? (
                    <>
                      <AlertTriangle className="h-4 w-4 text-amber-600" />
                      Deletion Preview
                    </>
                  ) : (
                    <>
                      <CheckCircle className="h-4 w-4 text-green-600" />
                      Deletion Complete
                    </>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <p className="text-xs text-muted-foreground">To Delete</p>
                    <p className="text-xl font-bold">{deleteResult.total_to_delete}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Deleted</p>
                    <p className="text-xl font-bold text-green-600">{deleteResult.total_deleted}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Errors</p>
                    <p className="text-xl font-bold text-red-600">{deleteResult.total_errors}</p>
                  </div>
                </div>

                {deleteResult.files_to_delete.length > 0 && (
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    <p className="text-sm font-medium">Files {deleteResult.dry_run ? "to be deleted" : "deleted"}:</p>
                    {deleteResult.files_to_delete.map((file, i) => (
                      <div key={i} className="text-xs font-mono p-2 bg-muted rounded">
                        <p className="truncate">{file.path}</p>
                        <p className="text-muted-foreground">Reason: {file.reason}</p>
                      </div>
                    ))}
                  </div>
                )}

                {deleteResult.errors.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-sm font-medium text-red-600">Errors:</p>
                    {deleteResult.errors.map((err, i) => (
                      <div key={i} className="text-xs p-2 bg-red-50 border border-red-200 rounded">
                        <p className="font-mono truncate">{err.path}</p>
                        <p className="text-red-600">{err.error}</p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {moveResult && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  {moveResult.dry_run ? (
                    <>
                      <AlertTriangle className="h-4 w-4 text-amber-600" />
                      Move Preview
                    </>
                  ) : (
                    <>
                      <CheckCircle className="h-4 w-4 text-green-600" />
                      Move Complete
                    </>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <p className="text-xs text-muted-foreground">To Move</p>
                    <p className="text-xl font-bold">{moveResult.total_to_move}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Moved</p>
                    <p className="text-xl font-bold text-green-600">{moveResult.total_moved}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Errors</p>
                    <p className="text-xl font-bold text-red-600">{moveResult.total_errors}</p>
                  </div>
                </div>

                {moveResult.destination_folder && (
                  <div className="p-2 bg-muted rounded">
                    <p className="text-xs text-muted-foreground">Destination:</p>
                    <p className="text-sm font-mono">{moveResult.destination_folder}</p>
                  </div>
                )}

                {moveResult.files_to_move.length > 0 && (
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    <p className="text-sm font-medium">Files {moveResult.dry_run ? "to be moved" : "moved"}:</p>
                    {moveResult.files_to_move.map((file, i) => (
                      <div key={i} className="text-xs font-mono p-2 bg-muted rounded">
                        <p className="truncate">{file.path}</p>
                        {file.destination && <p className="text-green-600 truncate">→ {file.destination}</p>}
                        <p className="text-muted-foreground">Reason: {file.reason}</p>
                      </div>
                    ))}
                  </div>
                )}

                {moveResult.errors.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-sm font-medium text-red-600">Errors:</p>
                    {moveResult.errors.map((err, i) => (
                      <div key={i} className="text-xs p-2 bg-red-50 border border-red-200 rounded">
                        <p className="font-mono truncate">{err.path}</p>
                        <p className="text-red-600">{err.error}</p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
