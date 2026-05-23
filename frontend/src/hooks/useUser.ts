import { useState, useEffect } from 'react'

interface User {
  email: string
  name: string
}

export function useUser() {
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    fetch('/me')
      .then(r => r.json())
      .then(setUser)
      .catch(() => setUser(null))  // fails gracefully in local dev
  }, [])

  return user
}