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

console = Console()

def get_price_data(code, days=30):
    end = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    df = fdr.DataReader(code, start, end)
    return df

def save_md(code, name, today_str, price, change, volume, high_30, low_30,
            df, fin, summary, news_list, disclosures):
    lines = []
    arrow = "▲" if change >= 0 else "▼"
    change_str = f"+{change*100:.2f}%" if change >= 0 else f"{change*100:.2f}%"

    lines.append(f"# 📊 {name} ({code}) | {today_str}\n")

    lines.append("## 현재가")
    lines.append(f"**{price:,}원** {arrow} {change_str}  (거래량 {volume:,}주)\n")

    lines.append("## 시세 요약")
    lines.append(f"| 구분 | 값 |")
    lines.append(f"|------|-----|")
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
    df = get_price_data(code)
    if df.empty:
        console.print(f"[red]{name} ({code}) — 데이터 없음[/red]")
        return

    latest  = df.iloc[-1]
    price   = int(latest["Close"])
    change  = latest["Change"]
    volume  = int(latest["Volume"])
    high_30 = int(df["High"].max())
    low_30  = int(df["Low"].min())

    change_str   = f"+{change*100:.2f}%" if change >= 0 else f"{change*100:.2f}%"
    change_color = "green" if change >= 0 else "red"
    arrow        = "▲" if change >= 0 else "▼"

    trend = ""
    if len(df) >= 20:
        ma5  = df["Close"].tail(5).mean()
        ma20 = df["Close"].tail(20).mean()
        trend = "  단기 [green]상승세[/green]" if ma5 > ma20 else "  단기 [red]하락세[/red]"

    # ── 헤더 + 현재가 한 줄
    console.print(
        f"\n[bold cyan]📊 {name}[/bold cyan] [dim]({code})[/dim]  "
        f"[bold]{price:,}원[/bold]  [{change_color}]{arrow} {change_str}[/{change_color}]"
        f"  [dim]거래량 {volume:,}  |  고 {high_30:,} / 저 {low_30:,}[/dim]{trend}"
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

    # ── MD 저장
    today_str = datetime.today().strftime("%Y-%m-%d")
    path = save_md(code, name, today_str, price, change, volume, high_30, low_30,
                   df, fin, summary, news_list, disclosures)
    console.print(f"  [dim]💾 {path}[/dim]")

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
