# 팜바톤 (FarmBaton)

고령 농가의 농장(농지+작목+시설+판로)을 청년농에게 잇는 승계 진단·매칭 플랫폼.
제11회 농업·농촌 공공데이터+AI 활용 창업경진대회 출품작.

상세 스코프·아키텍처·작업 방식은 [CLAUDE.md](./CLAUDE.md) 참고.

## 셋업

`pip install -r requirements.txt` 후, PDF 리포트 기능(`/api/farms/{id}/report.pdf`)에 필요한
headless Chromium을 1회 설치:

```
playwright install chromium
```
