'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

type Message = { role: 'user' | 'assistant'; content: string; reasoning?: string }

export default function Page() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [openMap, setOpenMap] = useState<Record<number, boolean>>({})
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const toggleThinking = (index: number) => {
    setOpenMap(prev => ({ ...prev, [index]: !prev[index] }))
  }

  const copyText = (text: string) => {
    navigator.clipboard.writeText(text)
  }

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || streaming) return
    const userMessage: Message = { role: 'user', content: text }
    const assistantMessage: Message = { role: 'assistant', content: '', reasoning: '' }
    setMessages(prev => [...prev, userMessage, assistantMessage])
    setInput('')
    setStreaming(true)
    try {
      const payload = {
        model: 'deepseek-reasoner',
        messages: [...messages, userMessage].map(m => ({ role: m.role, content: m.content })),
        stream: true
      }
      const res = await fetch('http://localhost:8000/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!res.body) throw new Error('no body')
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data:')) continue
          const data = trimmed.slice(5).trim()
          if (data === '[DONE]') continue
          try {
            const json = JSON.parse(data)
            const delta = json.choices?.[0]?.delta
            if (delta?.reasoning_content) {
              setMessages(prev => {
                const next = [...prev]
                const last = { ...next[next.length - 1] }
                last.reasoning = (last.reasoning ?? '') + delta.reasoning_content
                next[next.length - 1] = last
                return next
              })
            }
            if (delta?.content) {
              setMessages(prev => {
                const next = [...prev]
                const last = { ...next[next.length - 1] }
                last.content = (last.content ?? '') + delta.content
                next[next.length - 1] = last
                return next
              })
            }
          } catch {}
        }
      }
    } catch {
      setMessages(prev => {
        const next = [...prev]
        const last = { ...next[next.length - 1] }
        if (!last.content) last.content = 'Koneksi terputus.'
        next[next.length - 1] = last
        return next
      })
    } finally {
      setStreaming(false)
    }
  }, [input, streaming, messages])

  const clear = () => {
    setMessages([])
    setOpenMap({})
  }

  return (
    <div className="min-h-screen bg-[#070a0f] text-slate-200 font-mono flex flex-col">
      <header className="border-b border-[#00f0ff33] bg-[#0b0f17] px-6 py-4 flex items-center justify-between shadow-[0_0_24px_#00f0ff22]">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded border border-[#00f0ff] flex items-center justify-center text-[#00f0ff] shadow-[0_0_18px_#00f0ff]">
            R
          </div>
          <div>
            <h1 className="text-sm tracking-[0.3em] text-[#00f0ff]">ROBOT-DSK</h1>
            <p className="text-[10px] text-[#a855f7] tracking-[0.2em]">NEURAL LINK</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className={`h-2 w-2 rounded-full ${streaming ? 'bg-[#a855f7] animate-pulse' : 'bg-[#00f0ff]'}`} />
          <button
            onClick={clear}
            className="px-3 py-1 text-[11px] border border-[#a855f7] text-[#a855f7] rounded hover:bg-[#a855f7] hover:text-[#070a0f] transition"
          >
            Bersihkan
          </button>
        </div>
      </header>

      <main ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
        {messages.length === 0 && (
          <div className="text-center text-[#00f0ff55] mt-24 select-none">
            <div className="text-5xl mb-4">◈</div>
            <p className="text-xs tracking-[0.4em]">AWAITING INPUT</p>
          </div>
        )}
        {messages.map((msg, index) => (
          <div key={index} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] md:max-w-[70%] rounded-lg border px-4 py-3 ${
              msg.role === 'user'
                ? 'border-[#00f0ff] bg-[#00f0ff0d] text-[#cffafe] shadow-[0_0_16px_#00f0ff22]'
                : 'border-[#a855f7] bg-[#a855f70d] text-[#e9d5ff] shadow-[0_0_16px_#a855f722]'
            }`}>
              {msg.role === 'assistant' && msg.reasoning && (
                <div className="mb-3 border border-[#a855f7] rounded bg-[#0b0f17]">
                  <button
                    onClick={() => toggleThinking(index)}
                    className="w-full flex items-center justify-between px-3 py-2 text-[11px] text-[#a855f7] tracking-widest"
                  >
                    <span>Thinking</span>
                    <span>{openMap[index] ? '−' : '+'}</span>
                  </button>
                  {openMap[index] && (
                    <div className="px-3 pb-3 text-[11px] text-[#c084fc] whitespace-pre-wrap border-t border-[#a855f733]">
                      {msg.reasoning}
                    </div>
                  )}
                </div>
              )}
              <div className="whitespace-pre-wrap text-sm leading-relaxed">
                {msg.content}
                {streaming && index === messages.length - 1 && msg.role === 'assistant' && (
                  <span className="inline-block w-2 h-4 ml-1 bg-[#00f0ff] animate-pulse align-middle" />
                )}
              </div>
              {msg.role === 'assistant' && msg.content && (
                <div className="mt-2 flex justify-end">
                  <button
                    onClick={() => copyText(msg.content)}
                    className="text-[10px] px-2 py-0.5 border border-[#a855f7] text-[#a855f7] rounded hover:bg-[#a855f7] hover:text-[#070a0f] transition"
                  >
                    Salin
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
      </main>

      <footer className="border-t border-[#00f0ff33] bg-[#0b0f17] p-4">
        <div className="max-w-4xl mx-auto flex items-center gap-3">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder="Pesan"
            className="flex-1 bg-[#070a0f] border border-[#00f0ff55] rounded px-4 py-3 text-sm text-[#e2e8f0] placeholder-[#00f0ff44] outline-none focus:border-[#00f0ff] focus:shadow-[0_0_18px_#00f0ff44] transition"
          />
          <button
            onClick={send}
            disabled={streaming || !input.trim()}
            className="px-5 py-3 rounded border border-[#00f0ff] text-[#00f0ff] text-sm tracking-widest hover:bg-[#00f0ff] hover:text-[#070a0f] disabled:opacity-40 disabled:cursor-not-allowed transition shadow-[0_0_18px_#00f0ff33]"
          >
            {streaming ? 'Thinking' : 'Kirim'}
          </button>
        </div>
      </footer>
    </div>
  )
}
