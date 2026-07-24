// 면적 표기 헬퍼 — ha를 기본으로, 농가에 익숙한 평수를 괄호로 함께 표시.
// 1평 = 3.305785㎡ (3.3058로 환산).

const M2_PER_PYEONG = 3.305785

/** area_m2 → "1.66ha (약 1,660평)" */
export function formatArea(areaM2: number): string {
  const ha = (areaM2 / 10000).toFixed(2)
  const pyeong = Math.round(areaM2 / M2_PER_PYEONG)
  return `${ha}ha (약 ${pyeong.toLocaleString('ko-KR')}평)`
}

/** 만원 단위 금액: 1억원 이상은 억 단위, 미만은 만원 단위로 표시. */
export function formatManwon(value: number): string {
  if (Math.abs(value) >= 10_000) {
    return `${(value / 10_000).toLocaleString('ko-KR', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}억원`
  }
  return `${value.toLocaleString('ko-KR')}만원`
}

export function formatManwonRange(min: number, max: number): string {
  return `${formatManwon(min)} ~ ${formatManwon(max)}`
}
