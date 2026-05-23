import { Component } from 'react'
import type { ReactNode } from 'react'
import { ChatWindow } from './components/ChatWindow'

// Named interfaces keep the class generic on one line — avoids Vite 8 OXC parser bug
interface ErrorBoundaryProps { children: ReactNode }
interface ErrorBoundaryState { hasError: boolean; message: string }

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state = { hasError: false, message: '' }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, message: error.message }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center h-screen text-center p-8">
          <div>
            <p className="text-lg font-medium mb-2">Something went wrong</p>
            <p className="text-sm text-gray-500 mb-4">{this.state.message}</p>
            <button
              onClick={() => this.setState({ hasError: false, message: '' })}
              className="bg-blue-600 text-white px-4 py-2 rounded-full text-sm hover:bg-blue-700"
            >
              Try again
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

export default function App() {
  return (
    <ErrorBoundary>
      <ChatWindow />
    </ErrorBoundary>
  )
}