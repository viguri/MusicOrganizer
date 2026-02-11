import { create } from "zustand"
import type { WsMessage } from "@/hooks/useWebSocket"

interface TaskInfo {
  taskId: string
  type: string
  status: "running" | "completed" | "error"
  progress?: { current: number; total: number; percent: number; detail: string }
  result?: Record<string, unknown>
  error?: string
}

interface TaskStore {
  tasks: Record<string, TaskInfo>
  activeTaskId: string | null
  setActiveTask: (taskId: string | null) => void
  updateFromWs: (msg: WsMessage) => void
  clearTask: (taskId: string) => void
  clearAll: () => void
}

export const useTaskStore = create<TaskStore>((set) => ({
  tasks: {},
  activeTaskId: null,

  setActiveTask: (taskId) => set({ activeTaskId: taskId }),

  updateFromWs: (msg) =>
    set((state) => {
      const existing = state.tasks[msg.task_id] || {
        taskId: msg.task_id,
        type: "unknown",
        status: "running" as const,
      }

      const updated = { ...existing }

      if (msg.type === "progress") {
        updated.progress = {
          current: msg.current ?? 0,
          total: msg.total ?? 0,
          percent: msg.percent ?? 0,
          detail: msg.detail ?? "",
        }
      }

      if (msg.type === "status") {
        if (msg.status === "completed") updated.status = "completed"
        else if (msg.status === "error") {
          updated.status = "error"
          updated.error = msg.message
        } else {
          updated.status = "running"
        }
      }

      if (msg.type === "result") {
        updated.result = msg.data
      }

      return { tasks: { ...state.tasks, [msg.task_id]: updated } }
    }),

  clearTask: (taskId) =>
    set((state) => {
      const { [taskId]: _removed, ...rest } = state.tasks
      void _removed
      return { tasks: rest, activeTaskId: state.activeTaskId === taskId ? null : state.activeTaskId }
    }),

  clearAll: () => set({ tasks: {}, activeTaskId: null }),
}))
