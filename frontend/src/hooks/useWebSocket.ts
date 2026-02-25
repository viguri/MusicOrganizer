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
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true

    function connect() {
      if (!mountedRef.current) return

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
      const wsUrl = `${protocol}//${window.location.host}/ws`

      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        if (mountedRef.current) setConnected(true)
      }

      ws.onmessage = (event) => {
        if (!mountedRef.current) return
        try {
          const msg: WsMessage = JSON.parse(event.data as string)
          setMessages((prev) => [...prev.slice(-200), msg])
          setLastMessage(msg)
        } catch {
          // ignore non-JSON messages (e.g. "pong")
        }
      }

      ws.onclose = () => {
        if (!mountedRef.current) return
        setConnected(false)
        wsRef.current = null
        reconnectTimeout.current = setTimeout(connect, 3000)
      }

      ws.onerror = () => {
        if (mountedRef.current) ws.close()
      }
    }

    connect()
    return () => {
      mountedRef.current = false
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current)
      const ws = wsRef.current
      wsRef.current = null
      if (!ws) return

      // In React StrictMode, cleanup can run while socket is still CONNECTING.
      // Calling close() in that state emits a noisy browser warning.
      if (ws.readyState === WebSocket.CONNECTING) {
        ws.addEventListener("open", () => ws.close(), { once: true })
        return
      }

      ws.close()
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
