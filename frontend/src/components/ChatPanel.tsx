import { useEffect, useRef, useState } from 'react'
import { api, type ChatMessageItem } from '../api'

/**
 * 상담 채팅 패널 — 농장주·청년농 공용. consult_request 1건이 대화방 1개.
 * 4초 폴링으로 새 메시지를 가져온다(웹소켓 없이 데모에 충분).
 */
export default function ChatPanel({ reqId, title }: { reqId: number; title?: string }) {
  const [messages, setMessages] = useState<ChatMessageItem[]>([])
  const [enabled, setEnabled] = useState(true)
  const [body, setBody] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const load = async () => {
    try {
      const t = await api.getChatThread(reqId)
      setEnabled(t.chat_enabled)
      setMessages(prev => {
        // 메시지 수가 바뀐 경우에만 갱신해 불필요한 리렌더·스크롤 방지
        if (prev.length === t.messages.length) return prev
        return t.messages
      })
    } catch {
      setError('대화를 불러오지 못했습니다.')
    }
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 4000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reqId])

  useEffect(() => {
    listRef.current?.scrollTo(0, listRef.current.scrollHeight)
  }, [messages])

  const send = async (e: React.FormEvent) => {
    e.preventDefault()
    const text = body.trim()
    if (!text) return
    setSending(true)
    setError(null)
    try {
      const msg = await api.sendChatMessage(reqId, text)
      setMessages(m => [...m, msg])
      setBody('')
    } catch {
      setError('전송에 실패했습니다.')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="chat-panel">
      {title && <div className="chat-title">{title}</div>}
      <div className="chat-list" ref={listRef}>
        {messages.length === 0 ? (
          <div className="chat-empty">아직 대화가 없습니다. 먼저 인사를 건네보세요.</div>
        ) : (
          messages.map(m => (
            <div key={m.id} className={`chat-bubble ${m.mine ? 'mine' : 'theirs'}`}>
              <div className="chat-body">{m.body}</div>
              <div className="chat-time">{new Date(m.created_at).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</div>
            </div>
          ))
        )}
      </div>
      {error && <div className="error-box" style={{ marginTop: '.4rem' }}>{error}</div>}
      <form className="chat-input" onSubmit={send}>
        <input
          type="text"
          value={body}
          onChange={e => setBody(e.target.value)}
          placeholder={enabled ? '메시지를 입력하세요' : '수락된 후 대화할 수 있습니다'}
          disabled={!enabled || sending}
        />
        <button type="submit" className="btn btn-primary" disabled={!enabled || sending || !body.trim()}>
          전송
        </button>
      </form>
    </div>
  )
}
