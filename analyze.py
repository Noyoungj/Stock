import sys
import os
from dotenv import load_dotenv
load_dotenv()

import FinanceDataReader as fdr
from datetime import datetime, timedelta
from dart_client import find_stock_code, get_disclosures
from news_client import get_news
from financial_client import get_financial_data, summarize_financials


def fetch_and_print(code: str, name: str):
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"=== {name} ({code}) 분석 데이터 | {today} ===\n")

    # 가격 데이터
    end = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=30)).strftime("%Y-%m-%d")
    df = fdr.DataReader(code, start, end)

    if df.empty:
        print("가격 데이터를 가져오지 못했어요.")
    else:
        latest = df.iloc[-1]
        price  = int(latest["Close"])
        change = latest["Change"]
        volume = int(latest["Volume"])
        high_30 = int(df["High"].max())
        low_30  = int(df["Low"].min())
        arrow   = "▲" if change >= 0 else "▼"
        change_str = f"+{change*100:.2f}%" if change >= 0 else f"{change*100:.2f}%"

        print(f"[현재가]")
        print(f"  {price:,}원  {arrow} {change_str}  (거래량 {volume:,}주)")
        print(f"  30일 최고가: {high_30:,}원 / 최저가: {low_30:,}원")

        if len(df) >= 20:
            ma5  = df["Close"].tail(5).mean()
            ma20 = df["Close"].tail(20).mean()
            trend = "단기 상승세 (5일 이평 > 20일 이평)" if ma5 > ma20 else "단기 하락세 (5일 이평 < 20일 이평)"
            print(f"  이동평균 추세: {trend}")

        print()
        print("[최근 5일 시세]")
        recent = df.tail(5)[["Open", "High", "Low", "Close", "Volume"]].copy()
        recent.index = recent.index.strftime("%m/%d")
        for date, row in recent.iterrows():
            print(f"  {date}  시가 {int(row['Open']):,}  고가 {int(row['High']):,}  저가 {int(row['Low']):,}  종가 {int(row['Close']):,}  거래량 {int(row['Volume']):,}")

    print()

    # 재무 지표
    fin = get_financial_data(code)
    if fin:
        yr = fin.get("기준년도", "최근")
        ye = fin.get("예상년도", "예상")
        print(f"[재무 지표] ({yr} 기준, 예상: {ye})")
        for label, key, est_key in [
            ("매출액 (억원)",   "매출액",     None),
            ("영업이익 (억원)", "영업이익",   None),
            ("영업이익률 (%)",  "영업이익률", None),
            ("순이익 (억원)",   "순이익",     None),
            ("ROE (%)",          "ROE",         None),
            ("EPS (원)",         "EPS",         None),
            ("PER (배)",         "PER",         "PER_예상"),
            ("PBR (배)",         "PBR",         None),
            ("배당수익률 (%)",  "배당수익률", None),
        ]:
            val = fin.get(key, "-")
            est = f" / 예상 {fin.get(est_key, '-')}" if est_key else ""
            print(f"  {label}: {val}{est}")

        print()
        print("[재무 체크포인트]")
        for icon, text in summarize_financials(fin):
            print(f"  {icon} {text}")
    else:
        print("[재무 지표] 데이터를 가져오지 못했어요.")

    print()

    # 뉴스
    print("[최근 뉴스]")
    news_list = get_news(code)
    if news_list:
        for n in news_list:
            print(f"  - {n['title']}")
            print(f"    ({n['date']} / {n['source']}) {n['url']}")
    else:
        print("  뉴스 없음")

    print()

    # 공시
    print("[최근 2주 공시]")
    disclosures = get_disclosures(code)
    if disclosures:
        for d in disclosures:
            date = f"{d['date'][:4]}/{d['date'][4:6]}/{d['date'][6:]}"
            print(f"  - [{date}] {d['title']} ({d['submitter']})")
            print(f"    {d['url']}")
    else:
        print("  공시 없음")


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 analyze.py 005930")
        print("       python3 analyze.py 005930 삼성전자")
        sys.exit(1)

    code = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else code
    fetch_and_print(code, name)


if __name__ == "__main__":
    main()
