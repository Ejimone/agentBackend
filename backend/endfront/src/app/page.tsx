'use client';

import { useChat } from 'ai/react';
import { useEffect, useRef } from 'react';

export default function Chat() {
  const { messages, input, handleInputChange, handleSubmit } = useChat();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  return (
    <div className="min-h-screen bg-white flex flex-col">
      <div className="flex-1 mx-auto w-full max-w-2xl relative">
        {/* Messages container with hidden scrollbar */}
        <div className="absolute inset-0 overflow-y-auto pt-8 pb-32 px-4 scrollbar-hide">
          <div className="space-y-4">
            {messages.map(m => (
              <div 
                key={m.id} 
                className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div 
                  className={`
                    max-w-[80%] rounded-lg px-4 py-2
                    ${m.role === 'user' 
                      ? 'bg-blue-100 text-black' 
                      : 'bg-gray-100 text-black'}
                  `}
                >
                  <div className="text-xs text-gray-500 mb-1">
                    {/* {m.role === 'user' ? 'You' : 'Llama 3.3 70B powered by Groq'} */}
                  </div>
                  <div className="text-sm whitespace-pre-wrap">
                    {m.content}
                  </div>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} /> {/* Scroll anchor */}
          </div>
        </div>

        {/* Fixed input form at the bottom */}
        <div className="absolute bottom-0 left-0 right-0 bg-white p-4 border-t">
          <form onSubmit={handleSubmit} className="flex gap-4">
            <input
              value={input}
              onChange={handleInputChange}
              placeholder="Type your message..."
              className="flex-1 rounded-lg border border-gray-300 px-4 py-2 text-black focus:outline-none focus:ring-2 focus:ring-[#f55036]"
            />
            <button 
              type="submit"
              className="rounded-lg bg-[#f55036] px-4 py-2 text-white hover:bg-[#d94530] focus:outline-none focus:ring-2 focus:ring-[#f55036]"
            >
              Send
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
