import { Progress } from "@/components/ui/progress"
import { useTaskStore } from "@/stores/taskStore"

interface ProgressBarProps {
  taskId: string | null
}

export default function ProgressBar({ taskId }: ProgressBarProps) {
  const task = useTaskStore((s) => (taskId ? s.tasks[taskId] : undefined))

  if (!task?.progress) return null

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">{task.progress.detail}</span>
        <span className="font-medium">{task.progress.percent}%</span>
      </div>
      <Progress value={task.progress.percent} />
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {task.progress.current} / {task.progress.total}
        </span>
        <span className="capitalize">{task.status}</span>
      </div>
    </div>
  )
}
