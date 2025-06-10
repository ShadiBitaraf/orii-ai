import React, { useState, useRef, useEffect } from 'react';
import { Send, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import Message from './Message';

// Chrome extension types
declare global {
  interface Window {
    chrome?: typeof chrome;
  }
}

declare const chrome: any;

interface ChatMessage {
  id: string;
  content: string;
  isUser: boolean;
  timestamp: Date;
}

const ChatBar = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: '1',
      content: "Hello! I'm here to help you manage your calendar. What would you like to do today?",
      isUser: false,
      timestamp: new Date()
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [sessionId] = useState(() => `extension-${Date.now()}`);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Initialize side panel
  useEffect(() => {
    console.log('ORII Side Panel: Initialized and ready');
  }, []);

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isTyping) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      content: inputValue,
      isUser: true,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    const query = inputValue;
    setInputValue('');
    setIsTyping(true);

    // Check if we're in Chrome extension environment (side panel)
    if (typeof chrome !== 'undefined' && chrome.runtime) {
      // We're in Chrome extension side panel
      chrome.runtime.sendMessage({
        action: 'processQuery',
        query: query,
        sessionId: sessionId
      }, (response) => {
        setIsTyping(false);
        
        const responseText = response?.data?.response || response?.error || 'No response received';
        const aiMessage: ChatMessage = {
          id: (Date.now() + 1).toString(),
          content: responseText,
          isUser: false,
          timestamp: new Date()
        };

        setMessages(prev => [...prev, aiMessage]);
      });
    } else {
      // We're in standalone mode, call Flask API directly
      try {
        const response = await fetch('/api/query', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            query: query,
            session_id: sessionId
          })
        });

        const data = await response.json();
        setIsTyping(false);

        const aiMessage: ChatMessage = {
          id: (Date.now() + 1).toString(),
          content: data.response || data.error || 'No response received',
          isUser: false,
          timestamp: new Date()
        };

        setMessages(prev => [...prev, aiMessage]);
      } catch (error) {
        setIsTyping(false);
        const errorMessage: ChatMessage = {
          id: (Date.now() + 1).toString(),
          content: `Error connecting to ORII backend: ${error instanceof Error ? error.message : 'Unknown error'}`,
          isUser: false,
          timestamp: new Date()
        };
        setMessages(prev => [...prev, errorMessage]);
      }
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleCloseSidebar = () => {
    // In side panel mode, Chrome handles closing - we can close programmatically
    if (chrome && chrome.sidePanel) {
      // Close the side panel (this will work in Chrome 116+)
      window.close();
    } else {
      // Fallback for other environments
      console.log('Close button clicked - not in side panel environment');
    }
  };

  return (
    <div className="flex flex-col h-screen max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between py-4 px-6 border-b border-chat-border bg-white/50 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-gradient-to-r from-chat-pink to-chat-yellow flex items-center justify-center">
            <span className="font-bold text-white font-lg font-chango" style={{ textShadow: '2px 2px 4px rgba(0, 0, 0, 0.8)' }}>M</span>
          </div>
          <h1 className="text-lg font-semibold text-foreground">Calendar Assistant</h1>
        </div>
        <Button
          onClick={handleCloseSidebar}
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0 hover:bg-white/20 rounded-full transition-colors"
          title="Close ORII"
        >
          <X className="h-4 w-4 text-gray-600" />
        </Button>
      </div>

      {/* Messages Container */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message) => (
          <Message
            key={message.id}
            content={message.content}
            isUser={message.isUser}
            timestamp={message.timestamp}
          />
        ))}
        
        {isTyping && (
          <div className="flex justify-start">
            <div className="bg-white border border-chat-border rounded-2xl rounded-bl-md px-4 py-3 max-w-[70%]">
              <div className="flex space-x-1">
                <div className="w-2 h-2 bg-chat-pink rounded-full animate-bounce"></div>
                <div className="w-2 h-2 bg-chat-yellow rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                <div className="w-2 h-2 bg-chat-pink rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 border-t border-white/20 bg-transparent backdrop-blur-sm">
        <div className="flex gap-2 max-w-4xl mx-auto">
          <div className="flex-1 relative">
            <Input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Ask me anything about your calendar..."
              className="w-full rounded-2xl bg-white/80 backdrop-blur-sm border-white/30 focus:border-chat-pink focus:ring-chat-pink/20 pr-12 py-3 placeholder:text-gray-600"
              disabled={isTyping}
            />
          </div>
          <Button
            onClick={handleSendMessage}
            disabled={!inputValue.trim() || isTyping}
            className="rounded-2xl bg-gradient-to-r from-chat-pink to-chat-yellow hover:from-chat-pink-light hover:to-chat-yellow-light text-white shadow-lg transition-all duration-200 px-4"
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ChatBar;
