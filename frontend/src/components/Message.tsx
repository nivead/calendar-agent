import type { Message } from '../types'
import { EventCard } from './EventCard'

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div className={`max-w-[80%] ${isUser ? 'order-2' : 'order-1'}`}>

        {/* Tool call activity — shown above the reply */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mb-2 space-y-1">
            {message.toolCalls.map((tc, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-gray-500">
                <span className="w-2 h-2 rounded-full bg-blue-400"></span>
                <span className="font-mono">{tc.tool}</span>
                <span className="text-gray-400">→</span>
                <span className="text-gray-500 truncate max-w-[200px]">
                  {JSON.stringify(tc.args).slice(0, 60)}...
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Message bubble */}
        <div className={`rounded-2xl px-4 py-2.5 ${
          isUser
            ? 'bg-blue-600 text-white rounded-br-sm'
            : 'bg-gray-100 text-gray-900 rounded-bl-sm'
        }`}>
          <p className="text-sm leading-relaxed whitespace-pre-wrap">
            {message.content}
          </p>
        </div>

        {/* Event card — rendered below assistant reply if applicable */}
        {!isUser && message.toolCalls?.map((tc, i) =>
          tc.result ? <EventCard key={i} content={tc.result} /> : null
        )}
      </div>
    </div>
  )
}