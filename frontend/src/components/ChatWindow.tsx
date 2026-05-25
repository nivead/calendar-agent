import { useState, useRef, useEffect } from 'react'
import { useChat } from '../hooks/useChat'
import { useUser } from '../hooks/useUser'
import { MessageBubble } from './Message'

export function ChatWindow() {
  const [input, setInput] = useState('')
  const threadId          = useRef(crypto.randomUUID()).current
  const { messages, isLoading, activeTools, sendMessage } = useChat(threadId)
  const user              = useUser()
  const bottomRef         = useRef<HTMLDivElement>(null)

  const isOwner   = user?.is_owner   ?? true
  const ownerName = user?.owner_name ?? ''
  const welcomeName = user?.name ? `, ${user.name}` : ''

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, activeTools])

  const handleSend = () => {
    if (!input.trim()) return
    sendMessage(input)
    setInput('')
  }

  const signOutLink = user
    ? <a href="/logout" className="text-xs text-gray-400 hover:text-gray-600">Sign out</a>
    : <p className="text-xs text-gray-400">Powered by Claude</p>

  const userEmail = user
    ? <p className="text-xs text-gray-500">{user.email}</p>
    : null

  return (
    <div className="flex flex-col h-screen max-w-2xl mx-auto">

      {/* Header */}
      <div className="border-b px-4 py-3 flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center">
          <span className="text-white text-sm">📅</span>
        </div>
        <div className="flex-1">
          <p className="font-medium text-sm">
            {isOwner ? 'Calendar assistant' : `${ownerName}'s assistant`}
          </p>
          {userEmail}
        </div>
        {signOutLink}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-16 px-4">
            {isOwner ? (
              <>
                <p className="text-lg mb-2">👋 Hi{welcomeName}! What's on your agenda?</p>
                <p className="text-sm">Try: "What's on my calendar today?" or "Book a meeting tomorrow at 2pm"</p>
              </>
            ) : (
              <>
                <p className="text-lg mb-2">👋 Hi! I'm {ownerName}'s assistant.</p>
                <p className="text-sm">I can check their availability and book a meeting on your behalf.</p>
                <p className="text-sm mt-1">Try: "Is {ownerName} free tomorrow at 2pm?"</p>
              </>
            )}
          </div>
        )}

        {messages.map((msg: any) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {/* Live tool activity */}
        {isLoading && (
          <div className="flex justify-start mb-4">
            <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-4 py-2.5 max-w-[80%]">
              {activeTools.length > 0 ? (
                <div className="space-y-1">
                  {activeTools.map((tc: any, i: number) => (
                    <div key={i} className="flex items-center gap-2 text-xs text-gray-500">
                      <span className="animate-pulse w-2 h-2 rounded-full bg-blue-400"></span>
                      <span className="font-mono">{tc.tool}</span>
                      {tc.result && <span className="text-green-500">✓</span>}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex gap-1">
                  <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '0ms' }}></span>
                  <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '150ms' }}></span>
                  <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '300ms' }}></span>
                </div>
              )}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t px-4 py-3 flex gap-2">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
          placeholder={isOwner ? "Ask about your calendar..." : `Ask about ${ownerName}'s availability...`}
          disabled={isLoading}
          className="flex-1 border rounded-full px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={isLoading || !input.trim()}
          className="bg-blue-600 text-white rounded-full w-9 h-9 flex items-center justify-center disabled:opacity-50 hover:bg-blue-700 transition-colors"
        >
          ↑
        </button>
      </div>

    </div>
  )
}