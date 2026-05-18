import { useState, useCallback, useRef } from 'react'
import type { Message, ToolCall } from '../types'

export function useChat(threadId: string = 'default') {
  const [messages, setMessages]     = useState<Message[]>([])
  const [isLoading, setIsLoading]   = useState(false)
  const [activeTools, setActiveTools] = useState<ToolCall[]>([])
  const pendingToolsRef = useRef<ToolCall[]>([])

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isLoading) return

    // Add user message immediately
    const userMsg: Message = { id: crypto.randomUUID(), role: 'user', content }
    setMessages(prev => [...prev, userMsg])
    setIsLoading(true)
    pendingToolsRef.current = []

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: content, thread_id: threadId }),
      })

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        let eventType = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6))

            if (eventType === 'tool_call') {
              const tc: ToolCall = { tool: data.tool, args: data.args }
              pendingToolsRef.current = [...pendingToolsRef.current, tc]
              setActiveTools([...pendingToolsRef.current])
            }

            if (eventType === 'tool_result') {
              pendingToolsRef.current = pendingToolsRef.current.map(tc =>
                tc.tool === data.tool && !tc.result
                  ? { ...tc, result: data.content }
                  : tc
              )
              setActiveTools([...pendingToolsRef.current])
            }

            if (eventType === 'message') {
              const assistantMsg: Message = {
                id: crypto.randomUUID(),
                role: 'assistant',
                content: data.content,
                toolCalls: pendingToolsRef.current,
              }
              setMessages(prev => [...prev, assistantMsg])
              pendingToolsRef.current = []
              setActiveTools([])
            }

            if (eventType === 'error') {
              const errMsg: Message = {
                id: crypto.randomUUID(),
                role: 'assistant',
                content: `Error: ${data.message}`,
              }
              setMessages(prev => [...prev, errMsg])
            }
          }
        }
      }
    } finally {
      setIsLoading(false)
      setActiveTools([])
    }
  }, [isLoading, threadId])

  return { messages, isLoading, activeTools, sendMessage }
}