import os
import sys
import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.table import Table
from rich import box
from dotenv import load_dotenv

load_dotenv()

CA_BUNDLE = os.getenv("REQUESTS_CA_BUNDLE")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://finance.naver.com",
}
console = Console()


def fetch(url):
    res = requests.get(url, headers=HEADERS, verify=CA_BUNDLE, timeout=10)
    res.encoding = "euc-kr"
    return BeautifulSoup(res.text, "lxml")


def search_sectors(keyword):
    """업종 + 테마에서 키워드 검색 → (유형, 이름, no) 목록 반환"""
    results = []

    for sector_type, type_label in [("upjong", "업종"), ("theme", "테마")]:
        soup = fetch(f"https://finance.naver.com/sise/sise_group.naver?type={sector_type}")
        for a in soup.select("a[href*='sise_group_detail']"):
            name = a.get_text(strip=True)
            if keyword in name:
                href = a["href"]
                no = href.split("no=")[-1]
                results.append((sector_type, type_label, name, no))

    return results


def get_stocks_in_sector(sector_type, no, limit=10):
    """업종/테마 번호로 종목 목록 가져오기"""
    soup = fetch(
        f"https://finance.naver.com/sise/sise_group_detail.naver?type={sector_type}&no={no}"
    )

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

        price = tds[2].get_text(strip=True)
        change = tds[4].get_text(strip=True)

        if name and code:
            stocks.append({
                "name": name,
                "code": code,
                "price": price,
                "change": change,
            })

        if len(stocks) >= limit:
            break

    return stocks


def main():
    if len(sys.argv) < 2:
        console.print("[yellow]사용법: python3 search.py 반도체[/yellow]")
        sys.exit(1)

    keyword = sys.argv[1]
    console.print(f"\n[bold]'{keyword}' 관련 업종/테마 검색 중...[/bold]\n")

    sectors = search_sectors(keyword)

    if not sectors:
        console.print(f"[red]'{keyword}' 관련 업종/테마를 찾지 못했어요.[/red]")
        sys.exit(0)

    for sector_type, type_label, name, no in sectors:
        console.rule(f"[bold cyan]{type_label}: {name}[/bold cyan]")

        stocks = get_stocks_in_sector(sector_type, no)

        if not stocks:
            console.print("  [dim]종목 정보를 가져오지 못했어요.[/dim]\n")
            continue

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        table.add_column("종목명")
        table.add_column("종목코드")
        table.add_column("현재가", justify="right")
        table.add_column("등락률", justify="right")

        for s in stocks:
            change = s["change"]
            color = "green" if "+" in change else "red" if "-" in change else "dim"
            table.add_row(
                s["name"],
                s["code"],
                s["price"],
                f"[{color}]{change}[/{color}]",
            )

        console.print(table)

        # watchlist 추가 힌트
        codes = [f'"{s["code"]}": "{s["name"]}"' for s in stocks[:3]]
        console.print(
            f"  [dim]↑ report.py의 WATCHLIST에 추가하려면 종목코드를 복사하세요[/dim]\n"
        )


if __name__ == "__main__":
    main()
