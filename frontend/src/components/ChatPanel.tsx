import { Fragment, useEffect, useRef, useState } from 'react'
import { api, type ChatMessageItem } from '../api'

/**
 * 상담 채팅 패널 — 농장주·청년농 공용. consult_request 1건이 대화방 1개.
 * 4초 폴링으로 새 메시지를 가져온다(웹소켓 없이 데모에 충분).
 */
const initialOf = (name?: string) => (name || '?').trim().charAt(0) || '?'
const dayLabel = (iso: string) =>
  new Date(iso).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' })
const timeLabel = (iso: string) =>
  new Date(iso).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })

export default function ChatPanel({ reqId, name, subtitle }: { reqId: number; name?: string; subtitle?: string }) {
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
      {name && (
        <div className="chat-title">
          <div className="chat-head-id">
            <span className="chat-avatar" aria-hidden="true">{initialOf(name)}</span>
            <div className="chat-head-text">
              <div className="chat-head-name">{name}</div>
              {subtitle && <div className="chat-head-sub">{subtitle}</div>}
            </div>
          </div>
          <span className={`chat-status ${enabled ? 'enabled' : 'disabled'}`}>
            {enabled ? '대화 가능' : '수락 대기'}
          </span>
        </div>
      )}
      <div className="chat-list" ref={listRef} role="log" aria-live="polite">
        {messages.length === 0 ? (
          <div className="chat-empty">아직 대화가 없습니다.<br />먼저 인사를 건네보세요.</div>
        ) : (
          messages.map((m, i) => {
            const showDay = i === 0 || dayLabel(m.created_at) !== dayLabel(messages[i - 1].created_at)
            return (
              <Fragment key={m.id}>
                {showDay && (
                  <div className="chat-day"><span>{dayLabel(m.created_at)}</span></div>
                )}
                <div className={`chat-bubble ${m.mine ? 'mine' : 'theirs'}`}>
                  <div className="chat-body">{m.body}</div>
                  <div className="chat-time">{timeLabel(m.created_at)}</div>
                </div>
              </Fragment>
            )
          })
        )}
      </div>
      {error && <div className="chat-error error-box">{error}</div>}
      <form className="chat-input" onSubmit={send}>
        <textarea
          rows={1}
          value={body}
          onChange={e => setBody(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              e.currentTarget.form?.requestSubmit()
            }
          }}
          placeholder={enabled ? '메시지를 입력하세요' : '수락된 후 대화할 수 있습니다'}
          disabled={!enabled || sending}
        />
        <button
          type="submit"
          className="chat-send"
          aria-label="전송"
          disabled={!enabled || sending || !body.trim()}
        >
          {sending ? (
            <span className="spinner" />
          ) : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M22 2 11 13" />
              <path d="M22 2 15 22 11 13 2 9 22 2Z" />
            </svg>
          )}
        </button>
      </form>
    </div>
  )
}
