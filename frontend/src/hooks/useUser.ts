import { useState, useEffect } from 'react'

interface User {
  email:       string
  name:        string
  is_owner?:   boolean
  owner_name?: string
}

export function useUser() {
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    fetch('/me')
      .then(r => r.json())
      .then(data => setUser({
        email:      data.email      ?? '',
        name:       data.name       ?? '',
        is_owner:   data.is_owner   ?? true,  // default true = owner view
        owner_name: data.owner_name ?? '',
      }))
      .catch(() => setUser(null))
  }, [])

  return user
}