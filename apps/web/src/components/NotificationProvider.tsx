'use client'

import { createContext, useContext, useEffect, useState, useRef } from 'react'
import { api } from '@/lib/api'

interface NotificationContextType {
  notifications: any[]
  unreadCount: number
  markAsRead: (id: string) => void
  markAllAsRead: () => void
}

const NotificationContext = createContext<NotificationContextType>({
  notifications: [],
  unreadCount: 0,
  markAsRead: () => {},
  markAllAsRead: () => {}
})

export const useNotifications = () => useContext(NotificationContext)

export function NotificationProvider({ children, user }: { children: React.ReactNode, user: any }) {
  const [notifications, setNotifications] = useState<any[]>([])
  const ws = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!user) return

    // Fetch initial list
    api.get('/notifications').then(res => setNotifications(res.data)).catch(console.error)

    // Build WebSocket URL from env — never use window.location.host (that's the Next.js dev server)
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const wsBase =
      process.env.NEXT_PUBLIC_WS_URL ||
      apiUrl.replace(/^http/, 'ws')  // http → ws, https → wss
    const token = localStorage.getItem('access_token')
    const wsUrl = `${wsBase}/api/v1/ws/users/${user.id}${token ? `?token=${token}` : ''}`
    ws.current = new WebSocket(wsUrl)

    ws.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'notification.new') {
          // Prepend the new notification
          setNotifications(prev => [data.payload, ...prev])
        }
      } catch (err) {
        console.error(err)
      }
    }

    return () => {
      ws.current?.close()
    }
  }, [user])

  const unreadCount = notifications.filter(n => !n.read_at && n.is_read !== true).length

  const markAsRead = async (id: string) => {
    try {
      await api.post(`/notifications/${id}/read`)
      setNotifications(prev => prev.map(n => n.id === id ? { ...n, read_at: new Date().toISOString(), is_read: true } : n))
    } catch (e) {
      console.error(e)
    }
  }

  const markAllAsRead = async () => {
    // Left empty for now, could implement if needed
    setNotifications(prev => prev.map(n => ({ ...n, read_at: new Date().toISOString(), is_read: true })))
  }

  return (
    <NotificationContext.Provider value={{ notifications, unreadCount, markAsRead, markAllAsRead }}>
      {children}
    </NotificationContext.Provider>
  )
}

