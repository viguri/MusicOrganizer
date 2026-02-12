import { useState } from "react"
import { FileText, Play, Eye } from "lucide-react"
import { Button } from "@/components/ui/button"
import FolderPicker from "@/components/FolderPicker"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import ProgressBar from "@/components/ProgressBar"
import TaskStatus from "@/components/TaskStatus"
import { useTaskStore } from "@/stores/taskStore"
import { cleanNames, getOrganizeTaskStatus } from "@/lib/api"

interface NameChange {
  original: string
  cleaned: string
  path: string
}

export default function NameCleaner() {
  const [directory, setDirectory] = useState("")
  const [taskId, setTaskId] = useState<string | null>(null)
  const [result, setResult] = useState<{ total_renamed: number; dry_run: boolean; changes: NameChange[] } | null>(null)
  const [loading, setLoading] = useState(false)
  const tasks = useTaskStore((s) => s.tasks)

  const pollTask = (tid: string, onResult: (r: Record<string, unknown>) => void) => {
    const interval = setInterval(async () => {
      try {
        const status = await getOrganizeTaskStatus(tid)
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

  const handleClean = async (dryRun: boolean) => {
    if (!directory.trim()) return
    setLoading(true)
    setResult(null)
    try {
      const res = await cleanNames(directory.trim(), dryRun)
      setTaskId(res.task_id)
      pollTask(res.task_id, (r) => {
        setResult({
          total_renamed: r.total_renamed as number,
          dry_run: r.dry_run as boolean,
          changes: (r.changes ?? []) as NameChange[],
        })
      })
    } catch (e) {
      alert(String(e))
    } finally {
      setLoading(false)
    }
  }

  const task = taskId ? tasks[taskId] : undefined

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Name Cleaner</h2>
        <p className="text-muted-foreground">
          Remove URL spam, numeric prefixes, and normalize filenames
        </p>
      </div>

      <Card>
        <CardContent className="p-4 space-y-3">
          <FolderPicker
            value={directory}
            onChange={setDirectory}
            placeholder="Directory path to clean"
          />
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => handleClean(true)}
              disabled={loading || !directory.trim() || task?.status === "running"}
            >
              <Eye className="h-4 w-4" />
              Preview (Dry Run)
            </Button>
            <Button
              onClick={() => handleClean(false)}
              disabled={loading || !directory.trim() || task?.status === "running"}
            >
              <Play className="h-4 w-4" />
              Execute
            </Button>
          </div>
        </CardContent>
      </Card>

      {taskId && (
        <Card>
          <CardContent className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4" />
              <span className="text-sm font-medium">Progress</span>
              <TaskStatus taskId={taskId} />
            </div>
            <ProgressBar taskId={taskId} />
          </CardContent>
        </Card>
      )}

      {result && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {result.dry_run ? "Preview" : "Results"}: {result.total_renamed} files {result.dry_run ? "would be" : ""} renamed
            </CardTitle>
          </CardHeader>
          <CardContent>
            {result.changes.length === 0 ? (
              <p className="text-sm text-muted-foreground">No files need renaming.</p>
            ) : (
              <div className="border rounded-md overflow-auto max-h-96">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 sticky top-0">
                    <tr>
                      <th className="text-left p-2 font-medium">Original</th>
                      <th className="text-left p-2 font-medium">Cleaned</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.changes.map((c, i) => (
                      <tr key={i} className="border-t hover:bg-muted/30">
                        <td className="p-2 font-mono text-xs text-red-600 truncate max-w-sm">{c.original}</td>
                        <td className="p-2 font-mono text-xs text-green-600 truncate max-w-sm">{c.cleaned}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
