import { useEffect, useRef, useCallback, useState } from "react"

export interface WsMessage {
  type: "progress" | "status" | "result"
  task_id: string
  current?: number
  total?: number
  percent?: number
  detail?: string
  status?: string
  message?: string
  data?: Record<string, unknown>
}

interface UseWebSocketReturn {
  connected: boolean
  messages: WsMessage[]
  lastMessage: WsMessage | null
  clearMessages: () => void
  getTaskMessages: (taskId: string) => WsMessage[]
}

export function useWebSocket(): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const [messages, setMessages] = useState<WsMessage[]>([])
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null)
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    function connect() {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
      const wsUrl = `${protocol}//${window.location.host}/ws`

      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)

      ws.onmessage = (event) => {
        try {
          const msg: WsMessage = JSON.parse(event.data as string)
          setMessages((prev) => [...prev.slice(-200), msg])
          setLastMessage(msg)
        } catch {
          // ignore non-JSON messages (e.g. "pong")
        }
      }

      ws.onclose = () => {
        setConnected(false)
        wsRef.current = null
        reconnectTimeout.current = setTimeout(connect, 3000)
      }

      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current)
      wsRef.current?.close()
    }
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
    setLastMessage(null)
  }, [])

  const getTaskMessages = useCallback(
    (taskId: string) => messages.filter((m) => m.task_id === taskId),
    [messages]
  )

  return { connected, messages, lastMessage, clearMessages, getTaskMessages }
}
