
import React from 'react';
import { cn } from '@/lib/utils';

interface MessageProps {
  content: string;
  isUser: boolean;
  timestamp?: Date;
}

const Message = ({ content, isUser, timestamp }: MessageProps) => {
  return (
    <div className={cn(
      "flex w-full mb-4 animate-fade-in",
      isUser ? "justify-end" : "justify-start"
    )}>
      <div className={cn(
        "max-w-[70%] px-4 py-3 rounded-2xl shadow-sm",
        isUser 
          ? "bg-gradient-to-r from-chat-pink to-chat-yellow text-white rounded-br-md" 
          : "bg-white border border-chat-border text-foreground rounded-bl-md"
      )}>
        <p className="text-sm leading-relaxed">{content}</p>
        {timestamp && (
          <p className={cn(
            "text-xs mt-1 opacity-70",
            isUser ? "text-white" : "text-muted-foreground"
          )}>
            {timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </p>
        )}
      </div>
    </div>
  );
};

export default Message;
