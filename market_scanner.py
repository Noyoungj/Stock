import os
import sys
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import FinanceDataReader as fdr
from datetime import datetime, timedelta
from financial_client import get_financial_data, summarize_financials

load_dotenv()

CA = os.getenv("REQUESTS_CA_BUNDLE")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://finance.naver.com",
}


def fetch(url):
    res = requests.get(url, headers=HEADERS, verify=CA, timeout=10)
    res.encoding = "euc-kr"
    return BeautifulSoup(res.text, "lxml")


def get_market_index():
    """KOSPI/KOSDAQ 오늘 등락률"""
    results = {}
    for code, label in [("KS11", "KOSPI"), ("KQ11", "KOSDAQ")]:
        try:
            end = datetime.today().strftime("%Y-%m-%d")
            start = (datetime.today() - timedelta(days=5)).strftime("%Y-%m-%d")
            df = fdr.DataReader(code, start, end)
            if len(df) >= 2:
                chg = (df["Close"].iloc[-1] / df["Close"].iloc[-2] - 1) * 100
                results[label] = round(chg, 2)
        except Exception:
            results[label] = None
    return results


def get_sector_performance():
    """업종별 오늘 등락률 목록 반환"""
    soup = fetch("https://finance.naver.com/sise/sise_group.naver?type=upjong")
    sectors = []
    for row in soup.select("table.type_1 tr"):
        tds = row.select("td")
        if len(tds) < 2:
            continue
        name_tag = tds[0].select_one("a")
        if not name_tag:
            continue
        name = name_tag.get_text(strip=True)
        change_str = tds[1].get_text(strip=True)  # "+7.50%" 형태
        href = name_tag.get("href", "")
        no = href.split("no=")[-1] if "no=" in href else ""
        try:
            change = float(change_str.replace("%", "").replace("+", ""))
        except ValueError:
            continue
        sectors.append({"name": name, "change": change, "no": no})
    return sectors


def select_warming_sectors(sectors, min_chg=0.3, max_chg=4.0, top_n=3):
    """워밍업 업종 선별: 오늘 소폭 상승 중인 업종 (과열 제외)"""
    candidates = [s for s in sectors if min_chg <= s["change"] <= max_chg]
    candidates.sort(key=lambda x: x["change"], reverse=True)
    return candidates[:top_n]


def get_stocks_in_sector(no, limit=15):
    """업종 내 종목 목록"""
    soup = fetch(f"https://finance.naver.com/sise/sise_group_detail.naver?type=upjong&no={no}")
    stocks = []
    table = soup.select_one("table.type_5")
    if not table:
        return stocks
    for row in table.select("tr"):
        tds = row.select("td")
        if len(tds) < 5:
            continue
        name_tag = tds[0].select_one("a")
        if not name_tag:
            continue
        name = name_tag.get_text(strip=True)
        href = name_tag.get("href", "")
        code = href.split("code=")[-1] if "code=" in href else ""
        if name and code:
            stocks.append({"name": name, "code": code})
        if len(stocks) >= limit:
            break
    return stocks


def screen_stock(code):
    """
    4가지 조건 스크리닝
    반환: dict (조건 결과) 또는 None (데이터 없음)
    """
    try:
        end = datetime.today().strftime("%Y-%m-%d")
        start = (datetime.today() - timedelta(days=40)).strftime("%Y-%m-%d")
        df = fdr.DataReader(code, start, end)
        if len(df) < 20:
            return None

        # 조건 1: 최근 5일 주가 변동 -5%~+5% (아직 안 오름)
        price_5d_chg = (df["Close"].iloc[-1] / df["Close"].iloc[-6] - 1) * 100

        # 조건 2: 거래량 — 5일 평균 > 20일 평균 (관심 증가 중)
        vol_5  = df["Volume"].tail(5).mean()
        vol_20 = df["Volume"].tail(20).mean()
        vol_ratio = vol_5 / vol_20 if vol_20 > 0 else 0

        return {
            "price_5d_chg": round(price_5d_chg, 2),
            "vol_ratio":    round(vol_ratio, 2),
            "price":        int(df["Close"].iloc[-1]),
        }
    except Exception:
        return None


def score_stock(screen, fin):
    """
    조건별 점수 합산 (최대 4점)
    조건1: PER/PBR 낮고 ROE 양호
    조건2: 최근 5일 가격 변동 -5%~+5%
    조건3: 거래량 5일평균 > 20일평균
    조건4: 재무 체크포인트 긍정 수 > 부정 수
    """
    score = 0
    reasons = []

    # 조건 1: 밸류에이션
    if fin:
        try:
            per = float(fin.get("PER", "999").replace(",", ""))
            pbr = float(fin.get("PBR", "999").replace(",", ""))
            roe = float(fin.get("ROE", "0").replace(",", ""))
            if per < 15 and pbr < 3 and roe >= 8:
                score += 1
                reasons.append(f"저평가 (PER {per:.1f}배, PBR {pbr:.2f}배, ROE {roe:.1f}%)")
        except Exception:
            pass

    # 조건 2: 아직 안 오름
    if screen and -5 <= screen["price_5d_chg"] <= 5:
        score += 1
        reasons.append(f"최근 5일 변동 {screen['price_5d_chg']:+.1f}% (과열 아님)")

    # 조건 3: 거래량 증가
    if screen and screen["vol_ratio"] >= 1.15:
        score += 1
        reasons.append(f"거래량 5일평균이 20일평균 대비 {screen['vol_ratio']:.1f}배 (관심 증가)")

    # 조건 4: 재무 긍정 신호
    if fin:
        summary = summarize_financials(fin)
        positives = sum(1 for icon, _ in summary if icon in ("✅",))
        warnings  = sum(1 for icon, _ in summary if icon in ("⚠️ ",))
        if positives > warnings:
            score += 1
            reasons.append(f"재무 긍정 신호 {positives}개 > 주의 {warnings}개")

    return score, reasons


def run_scan(top_sectors=3):
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"=== 시장 스캔 결과 | {today} ===\n")

    # 지수
    indices = get_market_index()
    for label, chg in indices.items():
        arrow = "▲" if chg and chg >= 0 else "▼"
        chg_str = f"{chg:+.2f}%" if chg is not None else "N/A"
        print(f"  {label}: {arrow} {chg_str}")
    print()

    # 업종 스캔
    print("[업종 스캔]")
    all_sectors = get_sector_performance()
    warming = select_warming_sectors(all_sectors, top_n=top_sectors)

    if not warming:
        print("  워밍업 업종 없음 (전체 시장 과열 또는 하락장)")
        return

    candidates = []

    for sector in warming:
        print(f"\n  ▶ {sector['name']} ({sector['change']:+.2f}%) — 종목 스캔 중...")
        stocks = get_stocks_in_sector(sector["no"], limit=15)

        for s in stocks:
            screen = screen_stock(s["code"])
            if not screen:
                continue
            # 조건2 탈락 (이미 많이 오른 종목 제외)
            if not (-5 <= screen["price_5d_chg"] <= 5):
                continue

            fin = get_financial_data(s["code"])
            score, reasons = score_stock(screen, fin)

            if score >= 2:
                candidates.append({
                    "name":    s["name"],
                    "code":    s["code"],
                    "sector":  sector["name"],
                    "score":   score,
                    "reasons": reasons,
                    "screen":  screen,
                    "fin":     fin,
                })

    # 점수순 정렬, 상위 출력
    candidates.sort(key=lambda x: x["score"], reverse=True)

    print(f"\n{'='*50}")
    print(f"[후보 종목] (4개 조건 중 2개 이상 충족, 점수순)")
    print(f"{'='*50}\n")

    if not candidates:
        print("  조건 충족 종목 없음")
        return

    for c in candidates[:5]:
        print(f"★ {c['name']} ({c['code']}) | {c['sector']} | 점수 {c['score']}/4")
        print(f"  현재가: {c['screen']['price']:,}원")
        for r in c["reasons"]:
            print(f"  ✅ {r}")
        print()


if __name__ == "__main__":
    run_scan()
