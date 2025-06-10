import React from 'react';
import { cn } from '@/lib/utils';

interface MessageProps {
  content: string;
  isUser: boolean;
  timestamp?: Date;
}

const Message = ({ content, isUser, timestamp }: MessageProps) => {
  // Function to process the content and convert newlines and basic markdown
  const formatContent = (text: string) => {
    // Replace double newlines with paragraph breaks
    // Replace single newlines with br tags
    // Handle basic markdown bold syntax
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') // Bold text
      .replace(/\n\n/g, '</p><p>')  // Double newlines become paragraph breaks
      .replace(/\n/g, '<br/>');     // Single newlines become br tags
  };

  const formattedContent = formatContent(content);

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
        <div 
          className="text-sm leading-relaxed"
          dangerouslySetInnerHTML={{ __html: `<p>${formattedContent}</p>` }}
        />
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
