import { Link, useLocation } from 'react-router-dom'
import { useEffect, useRef } from 'react'
import heroFarm from '../assets/hero-farm.jpg'

function useHashScroll() {
  const { hash } = useLocation()
  useEffect(() => {
    if (!hash) return
    const el = document.querySelector(hash)
    if (el) setTimeout(() => el.scrollIntoView({ behavior: 'smooth' }), 80)
  }, [hash])
}

function useScrollReveal() {
  const rootRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const els = rootRef.current?.querySelectorAll<HTMLElement>('.reveal')
    if (!els || els.length === 0) return
    const obs = new IntersectionObserver(
      entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('in')
            obs.unobserve(entry.target)
          }
        })
      },
      { threshold: 0.15, rootMargin: '0px 0px -40px 0px' }
    )
    els.forEach(el => obs.observe(el))
    return () => obs.disconnect()
  }, [])
  return rootRef
}

export default function LandingPage() {
  const rootRef = useScrollReveal()
  useHashScroll()
  return (
    <div ref={rootRef}>
      {/* ════════ HERO ════════ */}
      <header className="lp-hero">
        <img src={heroFarm} alt="" className="lp-hero-photo" />
        <div className="lp-hero-overlay" />
        <div className="lp-wrap lp-hero-inner">
          <div className="lp-hero-content">
            <div className="lp-hero-text">
              <span className="lp-eyebrow" style={{ background: 'rgba(168,198,108,.18)', color: 'var(--lime)' }}>
                <span className="dot" style={{ background: 'var(--lime)' }}></span>농장 승계 진단 플랫폼
              </span>
              <h1>떠나는 농장과<br />시작하는 청년을 잇다</h1>
              <p className="lp-hero-lead">주소만 입력하면 농장의 인수 검토가 범위를 산출하고, 조건에 맞는 청년농과 연결합니다. 승계의 첫 숫자를 팜바톤에서.</p>
              <div className="lp-hero-actions">
                <Link className="lp-pill lp-pill-lime" to="/farmer">농가 등록하기 →</Link>
                <Link className="lp-pill lp-pill-ghost-light" to="/young">청년농으로 시작</Link>
              </div>
            </div>
            <div className="lp-glass">
              <h4><span className="dot"></span>우리의 미션</h4>
              <p>고령화로 멈추는 농장이 다음 세대로 이어지도록, 가치 산정부터 매칭까지 데이터로 돕습니다.</p>
            </div>
          </div>
        </div>
      </header>

      {/* ════════ FEATURES ════════ */}
      <section className="lp-features" id="features">
        <div className="lp-wrap">
          <div className="lp-sec-head">
            <span className="lp-eyebrow"><span className="dot"></span>WHAT WE DO</span>
            <h2>팜바톤이 하는 일</h2>
          </div>
          <div className="lp-feat-cards">
            <div className="lp-feat-card reveal">
              <div className="ic"><i></i></div>
              <h3>주소 한 줄로 진단</h3>
              <p>지번·도로명 주소만 입력하면 필지 면적을 자동으로 가져와 평가에 반영합니다.</p>
            </div>
            <div className="lp-feat-card lime reveal" style={{ transitionDelay: '.1s' }}>
              <div className="ic"><i></i></div>
              <h3>인수 검토가 범위</h3>
              <p>예상 소득·토지·시설 가치를 범위로 정리한 참고용 추정 리포트를 받습니다.</p>
            </div>
            <div className="lp-feat-card reveal" style={{ transitionDelay: '.2s' }}>
              <div className="ic"><i></i></div>
              <h3>청년농 매칭</h3>
              <p>지역·작목·자본 조건에 맞춰 승계 가능한 농장을 점수순으로 추천합니다.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ════════ 3-STEP STORY ════════ */}
      <section className="lp-steps" id="steps">
        <div className="lp-wrap">
          <div className="lp-sec-head">
            <span className="lp-eyebrow"><span className="dot"></span>3단계면 충분합니다</span>
            <h2>주소 입력부터 매칭까지, 이렇게 진행됩니다</h2>
          </div>

          <div className="lp-step-list">
            <div className="lp-step reveal">
              <div className="lp-step-copy">
                <div className="idx">01</div>
                <h3>주소·작목을 입력합니다</h3>
                <p>지번 또는 도로명 주소와 작목·수령을 넣으면, 필지 면적이 자동으로 채워집니다.</p>
                <span className="chip">소요 시간 약 1분</span>
              </div>
              <div className="lp-step-vis"><span>입력 화면 / 농장 사진</span></div>
            </div>

            <div className="lp-step flip reveal">
              <div className="lp-step-copy">
                <div className="idx">02</div>
                <h3>인수 검토 리포트를 받습니다</h3>
                <p>예상 소득·토지·시설 가치를 정리한 인수 검토가 범위(참고용 추정)를 신뢰등급과 함께 확인합니다.</p>
                <span className="chip">참고용 추정 · 신뢰등급 A~D</span>
              </div>
              <div className="lp-step-vis"><span>리포트 결과 화면 / 사진</span></div>
            </div>

            <div className="lp-step reveal">
              <div className="lp-step-copy">
                <div className="idx">03</div>
                <h3>청년농과 매칭됩니다</h3>
                <p>조건에 맞는 청년농을 매칭 점수순으로 추천받고, 승계 논의를 시작할 수 있습니다.</p>
                <span className="chip">지역·작목·자본 기준 매칭</span>
              </div>
              <div className="lp-step-vis"><span>매칭 리스트 화면 / 사진</span></div>
            </div>
          </div>
        </div>
      </section>

      {/* ════════ CTA ════════ */}
      <section className="lp-cta">
        <div className="lp-wrap">
          <div className="lp-cta-band reveal">
            <div>
              <h2>지금 내 농장부터 진단해 보세요</h2>
              <p>3분이면 충분합니다. 등록비 없이 시작할 수 있습니다.</p>
            </div>
            <Link className="lp-pill lp-pill-lime" to="/farmer">무료로 진단받기 →</Link>
          </div>
        </div>
      </section>

      {/* ════════ FOOTER ════════ */}
      <footer className="lp-foot">
        <div className="lp-wrap" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <span className="lp-logo"><span className="mark"><i></i></span>팜바톤</span>
          <p className="legal">본 서비스가 제공하는 모든 금액(인수 검토가 범위 포함)은 공개 통계와 입력 정보에 기반한 참고용 추정이며, 실제 거래가·감정평가액과 다를 수 있고 법적 효력이 없습니다.</p>
        </div>
      </footer>
    </div>
  )
}
