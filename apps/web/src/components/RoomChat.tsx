'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '@/lib/api'
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Loader2, Maximize2, Minimize2, MoreVertical, Copy, Bot, Users } from 'lucide-react'
import { Rnd } from 'react-rnd'
import { createPortal } from 'react-dom'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'

const WS_MAX_RETRIES = 8
const WS_BASE_DELAY_MS = 1000  // 1s -> 2s -> 4s -> 8s ... max ~128s + jitter

const getInitials = (name: string, email: string) => {
  if (name) return name.substring(0, 2).toUpperCase();
  if (email) return email.substring(0, 2).toUpperCase();
  return 'U';
}

export function RoomChat({ publicId, currentUser, aiPanel }: { publicId: string, currentUser: any, aiPanel?: React.ReactNode }) {
  const [room, setRoom] = useState<any>(null)
  const [messages, setMessages] = useState<any[]>([])
  const [inputValue, setInputValue] = useState('')
  const [typingUsers, setTypingUsers] = useState<Set<string>>(new Set())
  const [onlineUsers, setOnlineUsers] = useState<Set<string>>(new Set())
  const [connected, setConnected] = useState(false)
  const [isFloating, setIsFloating] = useState(false)

  const ws = useRef<WebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const typingTimeout = useRef<NodeJS.Timeout | null>(null)
  const retryCount = useRef(0)
  const retryTimer = useRef<NodeJS.Timeout | null>(null)
  const intentionalClose = useRef(false)

  const connectWsRef = useRef<((roomId: string) => void) | null>(null)

  const connectWs = useCallback((roomId: string) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) return

    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000'
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    const socketUrl = `${wsUrl}/api/v1/ws/rooms/${roomId}${token ? `?token=${encodeURIComponent(token)}` : ''}`
    const socket = new WebSocket(socketUrl)

    socket.onopen = () => {
      setConnected(true)
      retryCount.current = 0  // Reset backoff on successful connect
    }

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        switch (data.type) {
          case 'message.created':
            setMessages(prev => [...prev, data.payload])
            break
          case 'presence.updated':
            setOnlineUsers(prev => {
              const next = new Set(prev)
              if (data.payload.status === 'online') next.add(data.payload.user_id)
              else next.delete(data.payload.user_id)
              return next
            })
            break
          case 'typing.started':
            if (data.payload.user_id !== currentUser?.id) {
              setTypingUsers(prev => {
                const next = new Set(prev)
                next.add(data.payload.name || data.payload.user_id)
                return next
              })
            }
            break
          case 'typing.stopped':
            if (data.payload.user_id !== currentUser?.id) {
              setTypingUsers(prev => {
                const next = new Set(prev)
                next.delete(data.payload.name || data.payload.user_id)
                return next
              })
            }
            break
        }
      } catch {
        // Ignore malformed messages
      }
    }

    socket.onclose = (event) => {
      setConnected(false)

      if (intentionalClose.current) return  // User navigated away - don't reconnect

      if (retryCount.current >= WS_MAX_RETRIES) {
        if (process.env.NODE_ENV === 'development') {
          console.warn(`[RoomChat] Max WS retries (${WS_MAX_RETRIES}) reached. Giving up.`)
        }
        return
      }

      // Exponential backoff with jitter: 2^n * baseDelay ± 20% jitter
      const delay = Math.min(
        WS_BASE_DELAY_MS * Math.pow(2, retryCount.current),
        120_000  // Cap at 2 minutes
      ) * (0.8 + Math.random() * 0.4)  // ±20% jitter

      retryCount.current += 1
      retryTimer.current = setTimeout(() => {
        if (connectWsRef.current) connectWsRef.current(roomId)
      }, delay)
    }

    socket.onerror = () => {
      // onclose will fire after onerror - backoff handled there
      setConnected(false)
    }

    ws.current = socket
  }, [currentUser])

  useEffect(() => {
    connectWsRef.current = connectWs
  }, [connectWs])

  useEffect(() => {
    api.get(`/problems/${publicId}/room`).then(res => {
      const r = res.data
      setRoom(r)
      api.get(`/rooms/${r.id}/messages`).then(mRes => {
        setMessages(mRes.data)
      })
      connectWs(r.id)
    }).catch(err => {
      if (process.env.NODE_ENV === 'development') console.error('[RoomChat]', err)
    })

    return () => {
      intentionalClose.current = true
      if (retryTimer.current) clearTimeout(retryTimer.current)
      if (ws.current) ws.current.close()
    }
  }, [publicId, connectWs])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value)
    
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type: 'typing.started' }))
      
      if (typingTimeout.current) clearTimeout(typingTimeout.current)
      
      typingTimeout.current = setTimeout(() => {
        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
          ws.current.send(JSON.stringify({ type: 'typing.stopped' }))
        }
      }, 2000)
    }
  }

  const handleInvite = () => {
    navigator.clipboard.writeText(window.location.href)
    alert("Invite link copied to clipboard!")
  }

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!inputValue.trim() || !room) return
    
    try {
      const val = inputValue
      setInputValue('')
      if (ws.current && ws.current.readyState === WebSocket.OPEN) {
         ws.current.send(JSON.stringify({ type: 'typing.stopped' }))
      }
      await api.post(`/rooms/${room.id}/messages`, { content: val })
    } catch (err) {
      console.error(err)
    }
  }

  if (!room) return <div className="flex justify-center p-4"><Loader2 className="animate-spin text-primary" /></div>

  const chatContent = (
    <>
      <CardContent className="flex-1 overflow-y-auto p-4 space-y-4 bg-muted/10">
        {messages.length === 0 ? (
          <div className="text-center text-muted-foreground text-sm mt-4">
            Welcome to the problem room. Be the first to say hi!
          </div>
        ) : (
          messages.map(msg => {
            const isMe = Boolean(currentUser?.id && msg.author_id === currentUser.id)
            return (
              <div key={msg.id} className={`flex w-full ${isMe ? 'justify-end' : 'justify-start'}`}>
                <div className={`flex gap-2 max-w-[85%] ${isMe ? 'flex-row-reverse' : 'flex-row'}`}>
                  <div className="flex-shrink-0">
                    <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-xs font-bold text-primary">
                      {getInitials(msg.author_username, msg.author_email)}
                    </div>
                  </div>
                  <div className={`flex flex-col ${isMe ? 'items-end' : 'items-start'}`}>
                    <div className="text-xs text-muted-foreground mb-1 ml-1 mr-1">
                      {msg.author_username || msg.author_email || 'Unknown'}
                    </div>
                    <div className={`px-3 py-2 rounded-2xl ${isMe ? 'bg-primary text-primary-foreground rounded-tr-sm' : 'bg-white border text-foreground shadow-sm rounded-tl-sm'}`}>
                      <div className="text-sm whitespace-pre-wrap">{msg.content}</div>
                    </div>
                  </div>
                </div>
              </div>
            )
          })
        )}
        <div ref={messagesEndRef} />
      </CardContent>
      
      <CardFooter className="border-t p-3 flex-col items-start gap-2 bg-background mt-auto">
        {typingUsers.size > 0 && (
          <div className="text-xs text-muted-foreground italic h-4">
            {Array.from(typingUsers).join(', ')} {typingUsers.size > 1 ? 'are' : 'is'} typing...
          </div>
        )}
        <form onSubmit={handleSendMessage} className="flex w-full space-x-2">
          <Input 
            value={inputValue} 
            onChange={handleInputChange} 
            placeholder="Type a message..." 
            className="flex-1"
            disabled={!connected}
          />
          <Button type="submit" disabled={!connected || !inputValue.trim()}>Send</Button>
        </form>
      </CardFooter>
    </>
  )

  const RoomHeader = ({ showExpand = true }: { showExpand?: boolean }) => (
    <CardHeader className="border-b py-3 bg-background z-10 flex-shrink-0 cursor-move chat-drag-handle">
      <CardTitle className="text-lg flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span>Problem Room</span>
          <div className="flex items-center space-x-1 text-xs font-normal bg-muted px-2 py-1 rounded-full">
            <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-muted-foreground">{onlineUsers.size} Online</span>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {showExpand && (
            <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground" onClick={() => setIsFloating(!isFloating)}>
              {isFloating ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </Button>
          )}
          
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground" />}>
                <MoreVertical className="h-4 w-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={handleInvite} className="cursor-pointer">
                <Copy className="h-4 w-4 mr-2" /> Invite to Room
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </CardTitle>
    </CardHeader>
  )

  const innerContent = (
    <Card className="flex flex-col h-full w-full border-0 shadow-none sm:border sm:shadow-sm overflow-hidden bg-background">
      <RoomHeader />
      <Tabs defaultValue="chat" className="flex-1 flex flex-col h-[calc(100%-60px)]">
        {aiPanel && (
          <TabsList className="w-full justify-start rounded-none border-b bg-muted/30">
            <TabsTrigger value="chat" className="flex items-center gap-2"><Users className="w-4 h-4"/> Team Chat</TabsTrigger>
            <TabsTrigger value="ai" className="flex items-center gap-2"><Bot className="w-4 h-4"/> AI Agent</TabsTrigger>
          </TabsList>
        )}
        <TabsContent value="chat" className={`m-0 flex flex-col ${aiPanel ? 'h-[calc(100%-40px)]' : 'h-full'}`}>
          {chatContent}
        </TabsContent>
        {aiPanel && (
          <TabsContent value="ai" className="m-0 flex-1 overflow-auto p-4 h-[calc(100%-40px)]">
            {aiPanel}
          </TabsContent>
        )}
      </Tabs>
    </Card>
  )

  if (isFloating) {
    return (
      <>
        {/* Placeholder where the original chat was */}
        <div className="flex flex-col h-full border-2 border-dashed rounded-xl items-center justify-center p-6 text-center text-muted-foreground bg-muted/20">
          <Maximize2 className="w-8 h-8 mb-4 opacity-50" />
          <p>Chat is opened in floating mode.</p>
          <Button variant="outline" className="mt-4" onClick={() => setIsFloating(false)}>Restore Chat</Button>
        </div>
        
        {typeof document !== 'undefined' && createPortal(
          <Rnd
            default={{
              x: window.innerWidth / 2 - 400,
              y: window.innerHeight / 2 - 300,
              width: 800,
              height: 600,
            }}
            style={{ position: 'fixed', zIndex: 9999 }}
            minWidth={400}
            minHeight={400}
            bounds="window"
            dragHandleClassName=".chat-drag-handle"
            className="shadow-2xl rounded-xl overflow-hidden bg-background"
          >
            {innerContent}
          </Rnd>,
          document.body
        )}
      </>
    )
  }

  return innerContent
}
