interface Props {
  content: string
}

// Detect if a tool result contains event data and render a card
export function EventCard({ content }: Props) {
  // Simple heuristic — if it contains an ID and a time, it's an event
  const isEvent = content.includes('Event created') || content.includes('Event updated')

  if (!isEvent) return <p className="text-sm text-gray-600 mt-1">{content}</p>

  const lines = content.split('\n').filter(Boolean)
  return (
    <div className="mt-2 border border-green-200 bg-green-50 rounded-lg p-3 text-sm">
      {lines.map((line, i) => (
        <p key={i} className={i === 0 ? 'font-medium text-green-800' : 'text-green-700'}>
          {line}
        </p>
      ))}
    </div>
  )
}