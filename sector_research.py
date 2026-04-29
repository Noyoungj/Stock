import sys
import os
from dotenv import load_dotenv
load_dotenv()

import FinanceDataReader as fdr
from datetime import datetime, timedelta
from search import search_sectors, get_stocks_in_sector
from news_client import get_news
from financial_client import get_financial_data, summarize_financials

MAX_STOCKS_NEWS = 5   # 뉴스 수집할 종목 수
MAX_STOCKS_FIN  = 3   # 재무 수집할 종목 수 (느림)


def get_price_summary(code):
    try:
        end   = datetime.today().strftime("%Y-%m-%d")
        start = (datetime.today() - timedelta(days=30)).strftime("%Y-%m-%d")
        df = fdr.DataReader(code, start, end)
        if df.empty or len(df) < 5:
            return None
        price     = int(df["Close"].iloc[-1])
        chg_1d    = round((df["Close"].iloc[-1] / df["Close"].iloc[-2] - 1) * 100, 2)
        chg_5d    = round((df["Close"].iloc[-1] / df["Close"].iloc[-6] - 1) * 100, 2) if len(df) >= 6 else None
        chg_20d   = round((df["Close"].iloc[-1] / df["Close"].iloc[-21] - 1) * 100, 2) if len(df) >= 21 else None
        vol_ratio = round(df["Volume"].tail(5).mean() / df["Volume"].tail(20).mean(), 2) if len(df) >= 20 else None
        return {
            "price": price, "chg_1d": chg_1d,
            "chg_5d": chg_5d, "chg_20d": chg_20d,
            "vol_ratio": vol_ratio,
        }
    except Exception:
        return None


def run(keyword: str):
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"=== '{keyword}' 시장 조사 리포트 | {today} ===\n")

    # ── 1. 업종/테마 검색
    print(f"[관련 업종·테마]")
    sectors = search_sectors(keyword)
    if not sectors:
        print(f"  '{keyword}' 관련 업종·테마를 찾지 못했어요.")
        return

    for sector_type, type_label, name, no in sectors:
        print(f"  • {type_label}: {name}")
    print()

    # ── 2. 종목 수집 (첫 번째 섹터 기준, 여러 섹터면 합산)
    all_stocks = []
    seen_codes = set()
    for sector_type, type_label, name, no in sectors[:3]:
        stocks = get_stocks_in_sector(sector_type, no, limit=10)
        for s in stocks:
            if s["code"] not in seen_codes:
                all_stocks.append(s)
                seen_codes.add(s["code"])

    if not all_stocks:
        print("종목 데이터를 가져오지 못했어요.")
        return

    # ── 3. 주가 성과
    print(f"[주요 종목 현황]")
    print(f"{'종목명':<14} {'현재가':>9} {'오늘':>7} {'5일':>7} {'20일':>7} {'거래량비율':>8}")
    print("-" * 60)

    stocks_with_data = []
    for s in all_stocks[:10]:
        p = get_price_summary(s["code"])
        if not p:
            continue
        chg1  = f"{p['chg_1d']:+.1f}%" if p["chg_1d"]  is not None else "-"
        chg5  = f"{p['chg_5d']:+.1f}%" if p["chg_5d"]  is not None else "-"
        chg20 = f"{p['chg_20d']:+.1f}%" if p["chg_20d"] is not None else "-"
        vol   = f"{p['vol_ratio']:.2f}x"  if p["vol_ratio"] is not None else "-"
        print(f"{s['name']:<14} {p['price']:>9,} {chg1:>7} {chg5:>7} {chg20:>7} {vol:>8}")
        stocks_with_data.append({**s, **p})

    print()

    # ── 4. 업종 평균 수익률
    chg1d_list  = [s["chg_1d"]  for s in stocks_with_data if s.get("chg_1d")  is not None]
    chg5d_list  = [s["chg_5d"]  for s in stocks_with_data if s.get("chg_5d")  is not None]
    chg20d_list = [s["chg_20d"] for s in stocks_with_data if s.get("chg_20d") is not None]
    if chg1d_list:
        print(f"[섹터 평균 수익률]")
        print(f"  오늘: {sum(chg1d_list)/len(chg1d_list):+.2f}%  |  5일: {sum(chg5d_list)/len(chg5d_list):+.2f}%  |  20일: {sum(chg20d_list)/len(chg20d_list):+.2f}%")
        best  = max(stocks_with_data, key=lambda x: x.get("chg_5d") or -999)
        worst = min(stocks_with_data, key=lambda x: x.get("chg_5d") or 999)
        print(f"  5일 최강: {best['name']} ({best.get('chg_5d',0):+.1f}%)  |  최약: {worst['name']} ({worst.get('chg_5d',0):+.1f}%)")
    print()

    # ── 5. 뉴스 (상위 종목에서 수집)
    print(f"[관련 뉴스] (상위 {MAX_STOCKS_NEWS}개 종목에서 수집)")
    seen_titles = set()
    news_count = 0
    for s in stocks_with_data[:MAX_STOCKS_NEWS]:
        for n in get_news(s["code"], limit=3):
            title = n["title"]
            if title in seen_titles:
                continue
            seen_titles.add(title)
            print(f"  [{s['name']}] {n['date']}  {title}")
            print(f"    {n['url']}")
            news_count += 1
    if news_count == 0:
        print("  뉴스를 가져오지 못했어요.")
    print()

    # ── 6. 재무 요약 (상위 종목)
    print(f"[재무 하이라이트] (상위 {MAX_STOCKS_FIN}개 종목)")
    for s in stocks_with_data[:MAX_STOCKS_FIN]:
        fin = get_financial_data(s["code"])
        if not fin:
            continue
        print(f"\n  ▶ {s['name']} ({s['code']})")
        yr = fin.get("기준년도", "최근")
        print(f"    매출 {fin.get('매출액','-')}억  영업이익 {fin.get('영업이익','-')}억  영업이익률 {fin.get('영업이익률','-')}%")
        print(f"    PER {fin.get('PER','-')}배 / PBR {fin.get('PBR','-')}배 / ROE {fin.get('ROE','-')}% ({yr})")
        for icon, text in summarize_financials(fin):
            print(f"    {icon} {text}")
    print()


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 sector_research.py 반도체")
        sys.exit(1)
    run(sys.argv[1])


if __name__ == "__main__":
    main()
