export type Role = 'user' | 'assistant'

export interface Message {
  id: string
  role: Role
  content: string
  toolCalls?: ToolCall[]  // shown as activity indicators
}

export interface ToolCall {
  tool: string
  args: Record<string, unknown>
  result?: string
}