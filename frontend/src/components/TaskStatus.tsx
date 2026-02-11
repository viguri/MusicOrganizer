import { Badge } from "@/components/ui/badge"
import { Loader2, CheckCircle2, XCircle } from "lucide-react"
import { useTaskStore } from "@/stores/taskStore"

interface TaskStatusProps {
  taskId: string | null
}

export default function TaskStatus({ taskId }: TaskStatusProps) {
  const task = useTaskStore((s) => (taskId ? s.tasks[taskId] : undefined))

  if (!task) return null

  if (task.status === "running") {
    return (
      <Badge variant="secondary" className="gap-1">
        <Loader2 className="h-3 w-3 animate-spin" />
        Running
      </Badge>
    )
  }

  if (task.status === "completed") {
    return (
      <Badge className="gap-1 bg-green-600">
        <CheckCircle2 className="h-3 w-3" />
        Completed
      </Badge>
    )
  }

  if (task.status === "error") {
    return (
      <Badge variant="destructive" className="gap-1">
        <XCircle className="h-3 w-3" />
        Error
      </Badge>
    )
  }

  return null
}
