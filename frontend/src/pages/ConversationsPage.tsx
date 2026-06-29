import { useEffect, useState } from 'react'
import { api, type ConversationItem } from '../api'
import ChatPanel from '../components/ChatPanel'

/** 대화 메뉴 — 농장주·청년농 공용. 수락된 상담 = 대화방. 좌측 목록 + 우측 채팅. */
export default function ConversationsPage() {
  const [convos, setConvos] = useState<ConversationItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [active, setActive] = useState<ConversationItem | null>(null)

  useEffect(() => {
    api.getConversations()
      .then(list => {
        setConvos(list)
        setActive(prev => prev ?? list[0] ?? null)
      })
      .catch(err => setError(err.response?.data?.detail || '대화 목록을 불러오지 못했습니다.'))
  }, [])

  const handleDelete = async (c: ConversationItem, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm(`${c.counterpart_name}님과의 채팅을 삭제할까요?\n양쪽 모두에서 영구 삭제되며 되돌릴 수 없습니다.`)) return
    try {
      await api.deleteConversation(c.consult_request_id)
      setConvos(prev => (prev ?? []).filter(x => x.consult_request_id !== c.consult_request_id))
      setActive(a => (a?.consult_request_id === c.consult_request_id ? null : a))
    } catch {
      setError('채팅을 삭제하지 못했습니다.')
    }
  }

  const formatLastAt = (value: string | null) => {
    if (!value) return null
    return new Date(value).toLocaleString('ko-KR', {
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  return (
    <div className="page-wrap-wide convo-page">
      <header className="convo-page-head">
        <div>
          <p className="section-title">채팅</p>
        </div>
        {convos && convos.length > 0 && (
          <span className="convo-count">진행 {convos.length}건</span>
        )}
      </header>
      {error && <div className="error-box">{error}</div>}
      {convos === null ? (
        <div className="match-farm-meta">불러오는 중...</div>
      ) : convos.length === 0 ? (
        <div className="empty">
          <div style={{ fontSize: '2rem', marginBottom: '.5rem' }}>💬</div>
          아직 진행 중인 대화가 없습니다.<br />
          <span className="match-farm-meta">상담이 수락되면 여기에서 대화할 수 있습니다.</span>
        </div>
      ) : (
        <div className="convo-layout">
          <div className="convo-list">
            {convos.map(c => (
              <div className="convo-item-wrap" key={c.consult_request_id}>
              <button
                type="button"
                className={`convo-item ${active?.consult_request_id === c.consult_request_id ? 'active' : ''}`}
                aria-pressed={active?.consult_request_id === c.consult_request_id}
                onClick={() => setActive(c)}
              >
                <span className="convo-avatar" aria-hidden="true">
                  {(c.counterpart_name || '?').trim().charAt(0) || '?'}
                </span>
                <div className="convo-item-body">
                  <div className="convo-item-top">
                    <div className="convo-name">{c.counterpart_name}</div>
                    {c.last_message_at && (
                      <time className="convo-time" dateTime={c.last_message_at}>
                        {formatLastAt(c.last_message_at)}
                      </time>
                    )}
                  </div>
                  <div className="convo-meta">
                    {c.farm_label}
                    {c.initiated_by === 'FARMER' && <span className="convo-tag">농장주 발신</span>}
                  </div>
                  <div className="convo-preview">{c.last_message_preview || '아직 메시지가 없습니다'}</div>
                </div>
              </button>
              <button
                type="button"
                className="convo-del"
                aria-label="채팅 삭제"
                title="채팅 삭제"
                onClick={e => handleDelete(c, e)}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                  <path d="M10 11v6M14 11v6" />
                  <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                </svg>
              </button>
              </div>
            ))}
          </div>
          <div className="convo-chat">
            {active ? (
              <ChatPanel
                key={active.consult_request_id}
                reqId={active.consult_request_id}
                name={active.counterpart_name}
                subtitle={active.farm_label}
              />
            ) : (
              <div className="convo-chat-placeholder">대화를 선택하세요.</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
