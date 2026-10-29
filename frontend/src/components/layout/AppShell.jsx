import React, { useState } from 'react'
import { Sidebar } from './Sidebar'
import { ConversationView } from '../chat/ConversationView'
import { ChatProvider } from '../../context/ChatContext'

export function AppShell() {
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false)

  return (
    <ChatProvider>
      <div className="flex h-screen w-screen overflow-hidden bg-[#F2F2F7] dark:bg-neutral-950">
        {/* Desktop Sidebar */}
        <div className="hidden md:flex h-full">
          <Sidebar />
        </div>

        {/* Mobile Sidebar Slide-over Drawer */}
        {isMobileSidebarOpen && (
          <div className="fixed inset-0 z-50 flex md:hidden">
            {/* Backdrop */}
            <div
              className="fixed inset-0 bg-black/40 backdrop-blur-sm transition-opacity"
              onClick={() => setIsMobileSidebarOpen(false)}
            />
            {/* Drawer */}
            <div className="relative w-80 max-w-[85vw] h-full z-10 shadow-float animate-in slide-in-from-left duration-200">
              <Sidebar onCloseMobile={() => setIsMobileSidebarOpen(false)} />
            </div>
          </div>
        )}

        {/* Main Conversation Canvas */}
        <ConversationView
          onToggleSidebar={() => setIsMobileSidebarOpen(true)}
        />
      </div>
    </ChatProvider>
  )
}
