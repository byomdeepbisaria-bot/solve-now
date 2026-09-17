'use client'

import { Bell } from 'lucide-react'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel
} from '@/components/ui/dropdown-menu'
import { useNotifications } from './NotificationProvider'
import { useRouter } from 'next/navigation'
import { formatDistanceToNow } from 'date-fns'

export function NotificationBell() {
  const { notifications, unreadCount, markAsRead } = useNotifications()
  const router = useRouter()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="relative p-2 rounded-md hover:bg-muted/50 transition-colors focus:outline-none">
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-red-600 animate-pulse" />
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <div className="flex justify-between items-center px-2 py-1.5 text-sm font-semibold text-muted-foreground">
          <span>Notifications</span>
          {unreadCount > 0 && (
            <span className="text-xs bg-red-100 text-red-800 px-2 py-0.5 rounded-full">
              {unreadCount} new
            </span>
          )}
        </div>
        <DropdownMenuSeparator />
        <div className="max-h-[300px] overflow-y-auto">
          {notifications.length === 0 ? (
            <div className="p-4 text-center text-sm text-muted-foreground">
              No notifications yet.
            </div>
          ) : (
            notifications.slice(0, 10).map(n => (
              <DropdownMenuItem 
                key={n.id} 
                className={`flex flex-col items-start p-3 cursor-pointer ${(!n.read_at && n.is_read !== true) ? 'bg-muted/50' : ''}`}
                onClick={() => {
                  if (!n.read_at && n.is_read !== true) markAsRead(n.id)
                  if (n.action_url) router.push(n.action_url)
                }}
              >
                <div className="flex justify-between w-full">
                  <span className="font-semibold text-sm">{n.title}</span>
                  <span className="text-xs text-muted-foreground whitespace-nowrap ml-2">
                    {formatDistanceToNow(new Date(n.created_at))} ago
                  </span>
                </div>
                <span className="text-sm text-muted-foreground mt-1 line-clamp-2">{n.body}</span>
              </DropdownMenuItem>
            ))
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
