import sys
import os
from dotenv import load_dotenv
load_dotenv()

import FinanceDataReader as fdr
from datetime import datetime, timedelta
from dart_client import find_stock_code, get_disclosures
from news_client import get_news
from financial_client import get_financial_data, summarize_financials

POSITIVE_KEYWORDS = ["수주", "계약체결", "자사주", "매입", "실적", "흑자", "증가", "상향", "확대", "수출"]
NEGATIVE_KEYWORDS = ["조사", "과징금", "손실", "적자", "하향", "감소", "리콜", "소송", "제재"]


def screen(code: str, name: str):
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"=== {name} ({code}) 종목 스크리닝 | {today} ===\n")

    results = []

    # ── 가격/거래량 데이터
    end   = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=40)).strftime("%Y-%m-%d")
    df = fdr.DataReader(code, start, end)

    if df.empty or len(df) < 20:
        print("가격 데이터 부족으로 스크리닝 불가")
        return

    price      = int(df["Close"].iloc[-1])
    price_5d   = round((df["Close"].iloc[-1] / df["Close"].iloc[-6] - 1) * 100, 2)
    price_20d  = round((df["Close"].iloc[-1] / df["Close"].iloc[-21] - 1) * 100, 2)
    vol_5      = df["Volume"].tail(5).mean()
    vol_20     = df["Volume"].tail(20).mean()
    vol_ratio  = round(vol_5 / vol_20, 2) if vol_20 > 0 else 0
    high_20    = int(df["High"].tail(20).max())
    low_20     = int(df["Low"].tail(20).min())
    pct_from_high = round((price / high_20 - 1) * 100, 1)

    print(f"현재가: {price:,}원  |  20일 최고 대비 {pct_from_high:+.1f}%")
    print(f"최근 5일 수익률: {price_5d:+.2f}%  |  최근 20일 수익률: {price_20d:+.2f}%")
    print(f"거래량 비율 (5일평균/20일평균): {vol_ratio:.2f}배")
    print()

    # ── 조건 1: 저평가 + 실적 양호
    print("[조건 1] 저평가 + 실적 양호 (PER<15, PBR<3, ROE≥8%)")
    fin = get_financial_data(code)
    cond1 = False
    if fin:
        try:
            per = float(fin.get("PER", "999").replace(",", ""))
            pbr = float(fin.get("PBR", "999").replace(",", ""))
            roe = float(fin.get("ROE", "0").replace(",", ""))
            print(f"  PER {per:.1f}배 / PBR {pbr:.2f}배 / ROE {roe:.1f}%")
            if per < 15 and pbr < 3 and roe >= 8:
                cond1 = True
                print("  → ✅ 충족")
            else:
                reasons = []
                if per >= 15:  reasons.append(f"PER {per:.1f}배 (기준: <15)")
                if pbr >= 3:   reasons.append(f"PBR {pbr:.2f}배 (기준: <3)")
                if roe < 8:    reasons.append(f"ROE {roe:.1f}% (기준: ≥8%)")
                print(f"  → ❌ 미충족 ({', '.join(reasons)})")
        except Exception:
            print("  → ❓ 재무 데이터 파싱 실패")
    else:
        print("  → ❓ 재무 데이터 없음")
    results.append(cond1)

    # ── 조건 2: 최근 5일 변동 -5%~+5% (아직 안 오름)
    print()
    print("[조건 2] 최근 5일 주가 변동 -5%~+5% (과열·급락 제외)")
    cond2 = -5 <= price_5d <= 5
    if cond2:
        print(f"  {price_5d:+.2f}% → ✅ 충족")
    else:
        label = "이미 급등" if price_5d > 5 else "급락 중"
        print(f"  {price_5d:+.2f}% → ❌ 미충족 ({label})")
    results.append(cond2)

    # ── 조건 3: 거래량 증가 (5일평균 > 20일평균 × 1.15)
    print()
    print("[조건 3] 거래량 증가 (5일평균이 20일평균의 1.15배 이상)")
    cond3 = vol_ratio >= 1.15
    if cond3:
        print(f"  {vol_ratio:.2f}배 → ✅ 충족 (관심 유입 중)")
    else:
        print(f"  {vol_ratio:.2f}배 → ❌ 미충족 (거래량 아직 조용함)")
    results.append(cond3)

    # ── 조건 4: 최근 공시/뉴스 긍정 키워드
    print()
    print("[조건 4] 최근 공시·뉴스 긍정 신호")
    pos_count = neg_count = 0

    disclosures = get_disclosures(code, days=14)
    for d in disclosures:
        title = d.get("title", "")
        if any(k in title for k in POSITIVE_KEYWORDS): pos_count += 1
        if any(k in title for k in NEGATIVE_KEYWORDS): neg_count += 1

    news_list = get_news(code, limit=5)
    for n in news_list:
        title = n.get("title", "")
        if any(k in title for k in POSITIVE_KEYWORDS): pos_count += 1
        if any(k in title for k in NEGATIVE_KEYWORDS): neg_count += 1

    cond4 = pos_count > neg_count
    print(f"  긍정 키워드 {pos_count}건 / 부정 키워드 {neg_count}건")
    if cond4:
        print("  → ✅ 충족 (긍정 신호 우세)")
    elif pos_count == neg_count:
        print("  → ❓ 중립 (판단 유보)")
    else:
        print("  → ❌ 미충족 (부정 신호 우세)")
    results.append(cond4)

    # ── 최종 점수
    score = sum(results)
    print()
    print("=" * 40)
    print(f"최종 점수: {score}/4점")
    if score == 4:
        verdict = "강력 관심 — 4개 조건 모두 충족"
    elif score == 3:
        verdict = "관심 — 진입 검토 가능"
    elif score == 2:
        verdict = "보류 — 추가 확인 필요"
    else:
        verdict = "비추 — 조건 미달"
    print(f"판정: {verdict}")
    print("=" * 40)

    # ── 재무 요약 (Claude 분석용)
    if fin:
        print()
        print("[재무 체크포인트]")
        for icon, text in summarize_financials(fin):
            print(f"  {icon} {text}")


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 stock_screen.py 005930")
        print("       python3 stock_screen.py 005930 삼성전자")
        sys.exit(1)

    code = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else code
    screen(code, name)


if __name__ == "__main__":
    main()
