import { useState } from "react"
import { Copy, Play } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import ProgressBar from "@/components/ProgressBar"
import TaskStatus from "@/components/TaskStatus"
import { useTaskStore } from "@/stores/taskStore"
import { scanDuplicates, getOrganizeTaskStatus } from "@/lib/api"

interface DupeGroup {
  hash?: string
  key?: string
  files: string[]
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

  const handleScan = async () => {
    if (!source.trim()) return
    setLoading(true)
    setResult(null)
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
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Source Directory</label>
              <Input
                placeholder="Directory to scan for duplicates"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                className="font-mono text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Compare Against (optional)</label>
              <Input
                placeholder="Second directory to compare against"
                value={against}
                onChange={(e) => setAgainst(e.target.value)}
                className="font-mono text-sm"
              />
            </div>
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

      {result && (
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
                          {group.files.map((f, j) => (
                            <p key={j} className="text-xs font-mono truncate">{f}</p>
                          ))}
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
      )}
    </div>
  )
}
