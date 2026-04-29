# AI 투자 도우미 — 인수인계

## 현재 상태

Python으로 한국 주식 데이터 수집 + MD 리포트 생성까지 완성된 상태.
지금부터 할 것: **n8n 자동화 연결 + 티스토리 블로그 자동 발행**

---

## 완성된 것

| 파일 | 역할 |
|------|------|
| `report.py` | 워치리스트 종목 일일 브리핑 + MD 저장 (메인) |
| `dart_client.py` | OpenDART API — 공시 수집 |
| `news_client.py` | 네이버금융 — 뉴스 스크래핑 |
| `financial_client.py` | 네이버금융 — 재무지표 스크래핑 |
| `watchlist.py` | 관심종목 관리 |
| `analyze.py` | 단일 종목 상세 분석 |
| `stock_screen.py` | 단일 종목 4조건 스크리닝 |
| `market_scanner.py` | 시장 전체 스캔 → 후보 종목 |
| `sector_research.py` | 섹터/테마 리서치 |

---

## 목표 플로우 (n8n)

```
n8n Cron (매일 특정 시간)
    ↓
Execute Command → python3 report.py 실행
    ↓
Claude API → MD 내용 분석 + 블로그 글 작성
    ↓
티스토리 API → 자동 업로드
```

---

## 환경 세팅 (집 컴퓨터 기준)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install finance-datareader requests beautifulsoup4 lxml rich python-dotenv pandas
```

**.env 파일 생성:**
```
DART_API_KEY=발급된_키_입력
ANTHROPIC_API_KEY=발급된_키_입력
```
> 집 컴퓨터는 사내망 아니므로 REQUESTS_CA_BUNDLE 불필요

**n8n 설치:**
```bash
npm install -g n8n
npx n8n  # http://localhost:5678
```

---

## 필요한 API 키

| API | 상태 |
|-----|------|
| DART API 키 | ✅ 보유 |
| Claude API 키 | ✅ 보유 |
| 티스토리 API 키 | ❌ 발급 필요 (tistory.com/guide/api) |

---

## 다음 단계

1. 환경 세팅 확인 → `python3 report.py` 동작 테스트
2. 티스토리 API 키 발급
3. 블로그 글 양식 결정
4. n8n 워크플로우 구성
