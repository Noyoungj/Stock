import os
import sys
from dotenv import load_dotenv
load_dotenv()

import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime, timedelta
from rich.console import Console
from rich.table import Table
from rich import box
from dart_client import get_disclosures
from news_client import get_news
from financial_client import get_financial_data, summarize_financials
from watchlist import load as wl_load, cmd_add, cmd_remove, cmd_list
from chart_generator import generate_charts

console = Console()

def get_foreign_volume(code: str, days: int = 60):
    """네이버금융에서 외국인 순매매량(주) 수집. 실패 시 None 반환."""
    try:
        import requests
        from bs4 import BeautifulSoup
        import pandas as pd

        records = []
        for page in range(1, 4):  # 페이지당 약 30일, 최대 3페이지
            url = f"https://finance.naver.com/item/frgn.naver?code={code}&page={page}"
            hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            r = requests.get(url, headers=hdrs, timeout=5)
            soup = BeautifulSoup(r.text, "html.parser")

            tables = soup.find_all("table", {"class": "type2"})
            if len(tables) < 2:
                break

            for row in tables[1].find_all("tr"):
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cols) < 7 or not cols[0] or "." not in cols[0]:
                    continue
                try:
                    date_str = cols[0].replace(".", "-")
                    fv = int(cols[6].replace(",", "").replace("+", ""))
                    records.append({"date": date_str, "외국인순매수": fv})
                except (ValueError, IndexError):
                    continue

            if len(records) >= days:
                break

        if not records:
            return None

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df
    except Exception:
        return None


def get_price_data(code, days=30):
    end = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    df = fdr.DataReader(code, start, end)
    return df


def get_market_index():
    """코스피·코스닥 당일 지수 반환"""
    end = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=5)).strftime("%Y-%m-%d")
    result = {}
    for label, ticker in [("코스피", "KS11"), ("코스닥", "KQ11")]:
        try:
            df = fdr.DataReader(ticker, start, end)
            if not df.empty:
                latest = df.iloc[-1]
                result[label] = {
                    "close": float(latest["Close"]),
                    "change": float(latest["Change"]),
                }
        except Exception:
            pass
    return result

def make_foreign_signal(foreign_df, df):
    """외국인 순매수 패턴 해석. 신호 없거나 데이터 없으면 빈 리스트 반환."""
    if foreign_df is None or foreign_df.empty:
        return []

    signals = []
    try:
        aligned = foreign_df.reindex(df.index).dropna()
        if aligned.empty:
            return []

        fv = aligned["외국인순매수"]
        today_fv = int(fv.iloc[-1])
        today_change = df["Change"].iloc[-1]

        # ── 패턴 1: 연속 순매수/순매도 (3일 이상)
        streak, direction = 0, None
        for v in reversed(fv.values):
            cur = "매수" if v > 0 else "매도"
            if direction is None:
                direction, streak = cur, 1
            elif cur == direction:
                streak += 1
            else:
                break

        if streak >= 3:
            sign = "+" if today_fv >= 0 else ""
            if direction == "매수":
                signals.append(
                    f"외국인 {streak}일 연속 순매수 (오늘 +{today_fv/10000:.0f}만주) "
                    f"— 외국인 매집 가능성, 상승 모멘텀 주목"
                )
            else:
                signals.append(
                    f"외국인 {streak}일 연속 순매도 (오늘 {today_fv/10000:.0f}만주) "
                    f"— 외국인 이탈 지속, 하락 압력 주의"
                )

        # ── 패턴 2: 주가 방향과 외국인 방향 불일치
        if today_change > 0 and today_fv < 0:
            signals.append(
                f"오늘 주가 상승이나 외국인은 순매도 ({today_fv/10000:.0f}만주) "
                f"— 개인·기관 주도 상승, 지속성 약할 수 있음"
            )
        elif today_change < 0 and today_fv > 0:
            signals.append(
                f"오늘 주가 하락에도 외국인은 순매수 (+{today_fv/10000:.0f}만주) "
                f"— 외국인 저가 매집 가능성, 반등 여부 주목"
            )

        # ── 패턴 3: 오늘 거래 규모 급증 (20일 평균 대비 2배 이상)
        avg_abs = fv.abs().tail(20).mean()
        if avg_abs > 0 and abs(today_fv) >= avg_abs * 2 and abs(today_fv) > 100_000:
            label = "순매수" if today_fv >= 0 else "순매도"
            ratio = abs(today_fv) / avg_abs
            signals.append(
                f"오늘 외국인 {label} 규모 평소 대비 {ratio:.1f}배 — 강한 방향성 신호"
            )

    except Exception:
        pass

    return signals


def make_tomorrow_checkpoints(price, volume, df, high_52w, low_52w, news_list, disclosures,
                              foreign_df=None):
    """데이터 근거가 있는 항목만 체크포인트로 반환"""
    points = []

    # 외국인 패턴 (최우선)
    points.extend(make_foreign_signal(foreign_df, df))

    # 거래량: 오늘 vs 5일 평균
    avg_vol = df["Volume"].tail(5).mean()
    if avg_vol > 0:
        ratio = volume / avg_vol
        if ratio >= 1.5:
            points.append(f"오늘 거래량이 5일 평균 대비 {ratio:.1f}배 — 관심 급증, 내일 변동성 확인 필요")
        elif ratio <= 0.5:
            points.append(f"오늘 거래량이 5일 평균 대비 {ratio:.1f}배 — 관망세, 방향성 나올 때까지 지켜볼 필요")

    # 이동평균 추세
    if len(df) >= 20:
        ma5  = df["Close"].tail(5).mean()
        ma20 = df["Close"].tail(20).mean()
        if ma5 > ma20:
            points.append("5일 이평선이 20일 이평선 위 — 단기 상승 흐름 유지 중, 내일도 추세 지속 여부 확인")
        else:
            points.append("5일 이평선이 20일 이평선 아래 — 단기 하락 흐름, 반등 신호 나오는지 확인")

    # 52주 고저 근접 여부 (5% 이내)
    if high_52w > 0 and price >= high_52w * 0.95:
        points.append(f"현재가가 52주 최고가({high_52w:,}원)에 근접 — 저항 구간, 돌파 여부 주목")
    if low_52w > 0 and price <= low_52w * 1.05:
        points.append(f"현재가가 52주 최저가({low_52w:,}원)에 근접 — 지지 구간, 추가 하락 여부 확인")

    # 뉴스/공시 있으면
    if news_list:
        points.append("오늘 관련 뉴스 있음 — 내일 장 초반 시장 반응 확인 필요")
    if disclosures:
        points.append("오늘 공시 있음 — 공시 내용에 대한 시장 반응 내일 확인")

    return points


def save_md(code, name, today_str, price, change, volume, high_30, low_30,
            high_52w, low_52w, market_index, df, fin, summary, news_list, disclosures,
            foreign_df=None):
    lines = []
    arrow = "▲" if change >= 0 else "▼"
    change_str = f"+{change*100:.2f}%" if change >= 0 else f"{change*100:.2f}%"

    lines.append(f"# 📊 {name} ({code}) | {today_str}\n")

    lines.append("> 📌 이 글은 AI가 데이터를 분석해서 정리한 내용이에요. 주식 정보가 어디 있는지도 모르겠고, 찾아도 무슨 말인지 모르겠다는 분들을 위해 쓰고 있어요. 틀릴 수도 있으니 꼭 참고용으로만 봐주세요 😊\n")

    # ── 내일 체크포인트 (데이터 근거 있는 것만)
    checkpoints = make_tomorrow_checkpoints(price, volume, df, high_52w, low_52w, news_list, disclosures,
                                            foreign_df=foreign_df)
    if checkpoints:
        lines.append("## 내일 체크포인트")
        lines.append("> 데이터 기반 확인 포인트입니다. 예측이 아닙니다.")
        for pt in checkpoints:
            lines.append(f"- {pt}")
        lines.append("")

    # ── 시장 지수
    if market_index:
        idx_parts = []
        for label, v in market_index.items():
            c = v["change"]
            a = "▲" if c >= 0 else "▼"
            idx_parts.append(f"{label} {v['close']:,.2f} {a}{abs(c*100):.2f}%")
        lines.append("## 오늘 시장")
        lines.append("  |  ".join(idx_parts) + "\n")

    lines.append("## 현재가")
    lines.append(f"**{price:,}원** {arrow} {change_str}  (거래량 {volume:,}주)\n")

    lines.append("## 시세 요약")
    lines.append(f"| 구분 | 값 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 52주 최고가 | {high_52w:,}원 |")
    lines.append(f"| 52주 최저가 | {low_52w:,}원 |")
    lines.append(f"| 30일 최고가 | {high_30:,}원 |")
    lines.append(f"| 30일 최저가 | {low_30:,}원 |")
    lines.append(f"| 5일 평균 거래량 | {int(df['Volume'].tail(5).mean()):,}주 |")
    if len(df) >= 20:
        ma5 = df["Close"].tail(5).mean()
        ma20 = df["Close"].tail(20).mean()
        trend = "단기 상승세" if ma5 > ma20 else "단기 하락세"
        lines.append(f"| 이동평균 추세 | {trend} |")
    lines.append("")

    lines.append("## 최근 5일 시세")
    lines.append("| 날짜 | 시가 | 고가 | 저가 | 종가 | 거래량 |")
    lines.append("|------|------|------|------|------|--------|")
    recent = df.tail(5)[["Open", "High", "Low", "Close", "Volume"]].copy()
    recent.index = recent.index.strftime("%m/%d")
    for date, row in recent.iterrows():
        lines.append(f"| {date} | {int(row['Open']):,} | {int(row['High']):,} | {int(row['Low']):,} | {int(row['Close']):,} | {int(row['Volume']):,} |")
    lines.append("")

    lines.append("## 재무 지표")
    if fin:
        yr = fin.get("기준년도", "최근")
        ye = fin.get("예상년도", "예상")
        lines.append(f"| 항목 | {yr} | {ye} |")
        lines.append("|------|------|------|")
        for label, key, est_key in [
            ("매출액 (억원)", "매출액", None),
            ("영업이익 (억원)", "영업이익", None),
            ("영업이익률 (%)", "영업이익률", None),
            ("순이익 (억원)", "순이익", None),
            ("ROE (%)", "ROE", None),
            ("EPS (원)", "EPS", None),
            ("PER (배)", "PER", "PER_예상"),
            ("PBR (배)", "PBR", None),
            ("배당수익률 (%)", "배당수익률", None),
        ]:
            val = fin.get(key, "-")
            est = fin.get(est_key, "-") if est_key else "-"
            lines.append(f"| {label} | {val} | {est} |")
        lines.append("")

        lines.append("## 체크포인트")
        for icon, text in summary:
            lines.append(f"- {icon} {text}")
    else:
        lines.append("재무 데이터를 가져오지 못했어요.")
    lines.append("")

    lines.append("## 최근 뉴스")
    if news_list:
        for n in news_list:
            lines.append(f"- **{n['title']}**")
            lines.append(f"  {n['date']} | {n['source']} | [{n['url']}]({n['url']})")
    else:
        lines.append("뉴스 없음")
    lines.append("")

    lines.append("## 최근 2주 공시")
    if disclosures:
        for d in disclosures:
            date = f"{d['date'][:4]}/{d['date'][4:6]}/{d['date'][6:]}"
            lines.append(f"- **{d['title']}** ({d['submitter']})")
            lines.append(f"  {date} | [{d['url']}]({d['url']})")
    else:
        lines.append("공시 없음")
    lines.append("")

    lines.append("---")
    lines.append("> 투자 판단은 본인 몫입니다. 이 리포트는 정보 제공 목적입니다.")

    path = os.path.join(os.path.dirname(__file__), "reports", f"{name}_{code}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def print_report(code, name):
    # 365일 데이터로 52주 고저 + 30일 통계 모두 커버
    df = get_price_data(code, days=365)
    if df.empty:
        console.print(f"[red]{name} ({code}) — 데이터 없음[/red]")
        return

    latest   = df.iloc[-1]
    price    = int(latest["Close"])
    change   = latest["Change"]
    volume   = int(latest["Volume"])
    high_52w = int(df["High"].max())
    low_52w  = int(df["Low"].min())
    df30     = df.tail(30)
    high_30  = int(df30["High"].max())
    low_30   = int(df30["Low"].min())

    change_str   = f"+{change*100:.2f}%" if change >= 0 else f"{change*100:.2f}%"
    change_color = "green" if change >= 0 else "red"
    arrow        = "▲" if change >= 0 else "▼"

    trend = ""
    if len(df) >= 20:
        ma5  = df["Close"].tail(5).mean()
        ma20 = df["Close"].tail(20).mean()
        trend = "  단기 [green]상승세[/green]" if ma5 > ma20 else "  단기 [red]하락세[/red]"

    # ── 시장 지수
    market_index = get_market_index()
    if market_index:
        parts = []
        for label, v in market_index.items():
            a = "▲" if v["change"] >= 0 else "▼"
            c = "green" if v["change"] >= 0 else "red"
            parts.append(f"[dim]{label}[/dim] {v['close']:,.2f} [{c}]{a}{abs(v['change']*100):.2f}%[/{c}]")
        console.print("  " + "   ".join(parts))

    # ── 헤더 + 현재가
    console.print(
        f"\n[bold cyan]📊 {name}[/bold cyan] [dim]({code})[/dim]  "
        f"[bold]{price:,}원[/bold]  [{change_color}]{arrow} {change_str}[/{change_color}]"
        f"  [dim]거래량 {volume:,}[/dim]{trend}"
    )
    console.print(
        f"  [dim]52주  고 {high_52w:,} / 저 {low_52w:,}   30일  고 {high_30:,} / 저 {low_30:,}[/dim]"
    )

    # ── 재무 핵심 한 줄
    fin     = get_financial_data(code)
    summary = []
    if fin:
        summary = summarize_financials(fin)
        per = fin.get("PER", "-")
        per_e = fin.get("PER_예상", "-")
        pbr = fin.get("PBR", "-")
        roe = fin.get("ROE", "-")
        opm = fin.get("영업이익률", "-")
        console.print(
            f"  [dim]재무[/dim]  PER {per}배→{per_e}배  PBR {pbr}배  ROE {roe}%  영업이익률 {opm}%"
        )
        for icon, text in summary[:2]:
            console.print(f"  {icon} [dim]{text}[/dim]")

    # ── 뉴스 (화면 3개, MD 저장용 5개)
    news_list = get_news(code, limit=5)
    if news_list:
        console.print(f"  [dim]뉴스[/dim]  ", end="")
        for i, n in enumerate(news_list[:3]):
            prefix = "       " if i > 0 else ""
            console.print(f"{prefix}· {n['title']}  [dim]{n['date']}[/dim]")

    # ── 공시 (제목만 2개)
    disclosures = get_disclosures(code)
    if disclosures:
        console.print(f"  [dim]공시[/dim]  ", end="")
        for i, d in enumerate(disclosures[:2]):
            date = f"{d['date'][4:6]}/{d['date'][6:]}"
            prefix = "       " if i > 0 else ""
            console.print(f"{prefix}· [{date}] {d['title']}")

    # ── 외국인 순매수 (실패해도 계속 진행)
    foreign_df = get_foreign_volume(code)
    if foreign_df is not None:
        console.print(f"  [dim]외국인 순매수 데이터 수신 완료[/dim]")
    else:
        console.print(f"  [dim]외국인 데이터 없음 (네이버 스킵)[/dim]")

    # ── MD 저장
    today_str = datetime.today().strftime("%Y-%m-%d")
    path = save_md(code, name, today_str, price, change, volume, high_30, low_30,
                   high_52w, low_52w, market_index, df30, fin, summary, news_list, disclosures,
                   foreign_df=foreign_df)
    console.print(f"  [dim]💾 {path}[/dim]")

    # ── 차트 생성 (주가 차트는 365일, 거래량은 30일)
    chart_paths = generate_charts(code, name, df, fin, foreign_df)
    console.print(f"  [dim]📊 차트 {len(chart_paths)}개 생성[/dim]")
    return chart_paths

def main():
    args = sys.argv[1:]

    if args and args[0].lower() in ("add", "추가"):
        if len(args) < 2:
            console.print("[yellow]사용법: stock add 삼성전자[/yellow]")
            return
        cmd_add(" ".join(args[1:]))
        return

    if args and args[0].lower() in ("remove", "rm", "del", "삭제"):
        if len(args) < 2:
            console.print("[yellow]사용법: stock remove 삼성전자[/yellow]")
            return
        cmd_remove(" ".join(args[1:]))
        return

    if args and args[0].lower() in ("list", "ls", "목록"):
        cmd_list()
        return

    stocks = wl_load()
    if not stocks:
        console.print("[yellow]관심종목이 없어요.[/yellow]")
        console.print("[dim]추가하려면: stock add 삼성전자[/dim]")
        return

    today = datetime.today().strftime("%Y년 %m월 %d일")
    console.print(f"\n[bold white]AI 투자 도우미 — {today} 브리핑[/bold white]\n")

    for s in stocks:
        print_report(s["code"], s["name"])

if __name__ == "__main__":
    main()
