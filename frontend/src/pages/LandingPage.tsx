import { Link, useLocation } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import heroFarm from '../assets/hero-farm.jpg'
import stepInput from '../assets/step-1-input.png'
import stepReport from '../assets/step-2-report.png'
import stepMatch from '../assets/step-3-match.png'
import logoFull from '../assets/logo_full.png'

const INTRO_SESSION_KEY = 'fb_intro_shown'
const ENTRY_PREFERENCE_KEY = 'fb_entry_preference'

// 인트로: 드래그·휠·터치·키 외에 탭(클릭) 한 번으로도 닫히고,
// 조작이 없어도 2.6초 뒤 자동으로 넘어간다 (고령 사용자가 갇히지 않도록).
function useIntro() {
  const [show, setShow] = useState(() => !sessionStorage.getItem(INTRO_SESSION_KEY))
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!show) return
    sessionStorage.setItem(INTRO_SESSION_KEY, '1')
    const el = ref.current
    if (!el) return

    const THRESHOLD = 110 // 이만큼 끌어올린 채 놓으면 닫힘
    const SNAP = 'transform .42s cubic-bezier(.4,0,.2,1), opacity .42s ease'
    let done = false

    // y만큼 위로 이동 + 진행도에 따라 살짝 페이드. transition을 켜면 부드럽게 미끄러진다.
    const apply = (y: number, smooth: boolean) => {
      el.style.transition = smooth ? SNAP : 'none'
      el.style.transform = `translateY(${y}px)`
      el.style.opacity = String(Math.max(0, 1 + y / window.innerHeight))
    }

    const finish = () => {
      if (done) return
      done = true
      apply(-window.innerHeight, true) // 위로 완전히 밀어내고
      setTimeout(() => setShow(false), 420)
    }

    // 마우스 드래그(실시간 추적) — 리렌더 없이 DOM 직접 제어
    let startY: number | null = null
    let current = 0
    const onDown = (e: MouseEvent) => { startY = e.clientY; current = 0; el.style.transition = 'none' }
    const onMove = (e: MouseEvent) => {
      if (startY === null || done) return
      current = Math.min(0, e.clientY - startY) // 위로만 따라감
      apply(current, false)
    }
    const onUp = () => {
      if (startY === null) return
      startY = null
      if (current <= -THRESHOLD) finish()
      else apply(0, true) // 모자라면 제자리로 부드럽게 복귀
    }

    const opts: AddEventListenerOptions = { passive: true }
    const timer = window.setTimeout(finish, 2600) // 조작 없이도 자동 진입
    window.addEventListener('click', finish, opts) // 탭 한 번으로 즉시 진입
    window.addEventListener('wheel', finish, opts)
    window.addEventListener('touchmove', finish, opts)
    window.addEventListener('scroll', finish, opts)
    window.addEventListener('keydown', finish)
    window.addEventListener('mousedown', onDown, opts)
    window.addEventListener('mousemove', onMove, opts)
    window.addEventListener('mouseup', onUp, opts)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('click', finish)
      window.removeEventListener('wheel', finish)
      window.removeEventListener('touchmove', finish)
      window.removeEventListener('scroll', finish)
      window.removeEventListener('keydown', finish)
      window.removeEventListener('mousedown', onDown)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [show])
  return { show, ref }
}

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
  const intro = useIntro()
  useHashScroll()
  const rememberEntry = (entry: 'FARMER' | 'YOUNG') => {
    localStorage.setItem(ENTRY_PREFERENCE_KEY, entry)
  }
  return (
    <div ref={rootRef}>
      {intro.show && (
        <div
          ref={intro.ref}
          className="lp-intro"
          aria-hidden="true"
          style={{ cursor: 'grab', userSelect: 'none' }}
        >
          <img src={heroFarm} alt="" className="lp-intro-photo" />
          <div className="lp-intro-overlay" />
          <div className="lp-intro-text">
            <p>떠나는 농장의 가치를 이어갑니다</p>
            <p className="lime">경험은 남기고, 청년의 꿈은 자라납니다.</p>
          </div>
          <div className="lp-intro-hint">
            <span>화면을 누르면 바로 시작합니다</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="6 9 12 15 18 9" />
              <polyline points="6 14 12 20 18 14" />
            </svg>
          </div>
        </div>
      )}
      {/* ════════ HERO ════════ */}
      <header className="lp-hero">
        <img src={heroFarm} alt="" className="lp-hero-photo" />
        <div className="lp-hero-overlay" />
        <div className="lp-wrap lp-hero-inner">
          <div className="lp-hero-content">
            <div className="lp-hero-text">
              <span className="lp-eyebrow" style={{ background: 'rgba(168,198,108,.18)', color: 'var(--lime)' }}>
                농장 승계 진단 플랫폼
              </span>
              <h1>떠나는 농장과<br />시작하는 청년을 잇다</h1>
              <p className="lp-hero-tagline">고령 농가의 농장을 청년농에게 잇는 승계 진단·매칭 서비스</p>
              <p className="lp-hero-lead">주소만 입력하면 농장의 인수 검토가 범위를 산출하고, 조건에 맞는 청년농과 연결합니다. 승계의 첫 숫자를 팜바톤에서.</p>
            </div>
            <section className="lp-role-chooser" aria-labelledby="entry-choice-title">
              <div className="lp-role-chooser-head">
                <span className="lp-role-chooser-eyebrow">어떤 도움을 원하시나요?</span>
                <h2 id="entry-choice-title">나에게 맞는 방식으로<br />시작해 보세요</h2>
              </div>
              <div className="lp-role-cards">
                <Link className="lp-role-card lp-role-card-farmer" to="/farmer" onClick={() => rememberEntry('FARMER')}>
                  <span className="lp-role-card-index" aria-hidden="true">01</span>
                  <strong>내 농장을<br />정리하고 싶어요</strong>
                  <span>농장 등록과 인수 검토 결과 확인</span>
                  <b>농장주로 시작하기 <i aria-hidden="true">→</i></b>
                </Link>
                <Link className="lp-role-card lp-role-card-young" to="/young" onClick={() => rememberEntry('YOUNG')}>
                  <span className="lp-role-card-index" aria-hidden="true">02</span>
                  <strong>이어받을 농장을<br />찾고 있어요</strong>
                  <span>희망 조건에 맞는 농장 추천</span>
                  <b>청년농으로 시작하기 <i aria-hidden="true">→</i></b>
                </Link>
              </div>
              <p className="lp-role-chooser-note">선택은 언제든 바꿀 수 있어요.</p>
            </section>
          </div>
        </div>
      </header>

      {/* ════════ FEATURES ════════ */}
      <section className="lp-features" id="features">
        <div className="lp-wrap">
          <div className="lp-sec-head">
            <h2>팜바톤이 하는 일</h2>
          </div>
          <div className="lp-feat-cards">
            <div className="lp-feat-card reveal">
              <h3>주소 한 줄로 진단</h3>
              <p>지번·도로명 주소만 입력하면 필지 면적을 자동으로 가져와 평가에 반영합니다.</p>
            </div>
            <div className="lp-feat-card reveal" style={{ transitionDelay: '.1s' }}>
              <h3>인수 검토가 범위</h3>
              <p>예상 소득·토지·시설 가치를 범위로 정리한 참고용 추정 리포트를 받습니다.</p>
            </div>
            <div className="lp-feat-card reveal" style={{ transitionDelay: '.2s' }}>
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
            <span className="lp-eyebrow">3단계면 충분합니다</span>
            <h2>주소 입력부터 매칭까지, 이렇게 진행됩니다</h2>
          </div>

          <div className="lp-step-list">
            <div className="lp-step reveal">
              <div className="lp-step-copy">
                <div className="idx">01</div>
                <h3>주소·작목을 입력합니다</h3>
                <p>지번 또는 도로명 주소와 작목·수령을 넣으면, 필지 면적이 자동으로 채워집니다.</p>
              </div>
              <div className="lp-step-vis"><img src={stepInput} alt="주소·작목 입력 화면" loading="lazy" /></div>
            </div>

            <div className="lp-step flip reveal">
              <div className="lp-step-copy">
                <div className="idx">02</div>
                <h3>인수 검토 리포트를 받습니다</h3>
                <p>예상 소득·토지·시설 가치를 정리한 인수 검토가 범위(참고용 추정)를 신뢰등급과 함께 확인합니다.</p>
                <span className="chip">참고용 추정 · 신뢰등급 A~D</span>
              </div>
              <div className="lp-step-vis"><img src={stepReport} alt="인수 검토가 범위 리포트 결과 화면" loading="lazy" /></div>
            </div>

            <div className="lp-step reveal">
              <div className="lp-step-copy">
                <div className="idx">03</div>
                <h3>청년농과 매칭됩니다</h3>
                <p>조건에 맞는 청년농을 매칭 점수순으로 추천받고, 승계 논의를 시작할 수 있습니다.</p>
                <span className="chip">지역·작목·자본 기준 매칭</span>
              </div>
              <div className="lp-step-vis"><img src={stepMatch} alt="청년농 매칭 리스트 화면" loading="lazy" /></div>
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
            <Link className="lp-pill lp-pill-warm" to="/farmer">무료로 진단받기 →</Link>
          </div>
        </div>
      </section>

      {/* ════════ FOOTER ════════ */}
      <footer className="lp-foot">
        <div className="lp-wrap" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <img src={logoFull} className="lp-foot-logo-img" alt="팜바톤" />
          <p className="legal">본 서비스가 제공하는 모든 금액(인수 검토가 범위 포함)은 공개 통계와 입력 정보에 기반한 참고용 추정이며, 실제 거래가·감정평가액과 다를 수 있고 법적 효력이 없습니다.</p>
        </div>
      </footer>
    </div>
  )
}
