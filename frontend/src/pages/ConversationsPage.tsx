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
          <p className="section-title">대화</p>
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
              <button
                type="button"
                key={c.consult_request_id}
                className={`convo-item ${active?.consult_request_id === c.consult_request_id ? 'active' : ''}`}
                aria-pressed={active?.consult_request_id === c.consult_request_id}
                onClick={() => setActive(c)}
              >
                <div className="convo-item-top">
                  <div className="convo-name">{c.counterpart_name}</div>
                  {c.last_message_at && (
                    <time className="convo-time" dateTime={c.last_message_at}>
                      {formatLastAt(c.last_message_at)}
                    </time>
                  )}
                </div>
                <div className="convo-meta">{c.farm_label}{c.initiated_by === 'FARMER' ? ' · 농장주 발신' : ''}</div>
                <div className="convo-preview">{c.last_message_preview || '아직 메시지가 없습니다'}</div>
              </button>
            ))}
          </div>
          <div className="convo-chat">
            {active ? (
              <ChatPanel
                key={active.consult_request_id}
                reqId={active.consult_request_id}
                title={`${active.counterpart_name} · ${active.farm_label}`}
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
