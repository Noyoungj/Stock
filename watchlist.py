import sys
import json
import os
from rich.console import Console
from rich.table import Table
from rich import box
from dart_client import find_stock_code, find_name_by_code

WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlist.json")

console = Console()


def load():
    if not os.path.exists(WATCHLIST_FILE):
        return []
    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save(data):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def cmd_list():
    stocks = load()
    if not stocks:
        console.print("[yellow]워치리스트가 비어 있어요.[/yellow]")
        console.print("[dim]추가: python3 watchlist.py add 삼성전자[/dim]")
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("번호", justify="right", style="dim")
    table.add_column("회사명")
    table.add_column("종목코드")

    for i, s in enumerate(stocks, 1):
        table.add_row(str(i), s["name"], s["code"])

    console.print(f"\n[bold]관심종목 {len(stocks)}개[/bold]\n")
    console.print(table)


def cmd_add(keyword):
    # 6자리 코드 직접 입력
    if keyword.isdigit() and len(keyword) == 6:
        name = find_name_by_code(keyword)
        if not name:
            console.print(f"[red]종목코드 {keyword} 를 찾을 수 없어요.[/red]")
            return
        stocks = load()
        if any(s["code"] == keyword for s in stocks):
            console.print(f"[yellow]{name} ({keyword}) 은 이미 워치리스트에 있어요.[/yellow]")
            return
        stocks.append({"name": name, "code": keyword})
        save(stocks)
        console.print(f"[green]✅ {name} ({keyword}) 추가됨[/green]")
        return

    results = find_stock_code(keyword)

    if not results:
        console.print(f"[red]'{keyword}' 와 일치하는 종목이 없어요.[/red]")
        console.print("[dim]줄임말 대신 정식 회사명으로 검색해보세요. (예: 현대차 → 현대자동차)[/dim]")
        return

    if len(results) == 1:
        name, code = results[0]
    else:
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        table.add_column("번호", justify="right", style="dim")
        table.add_column("회사명")
        table.add_column("종목코드")
        for i, (n, c) in enumerate(results[:20], 1):
            table.add_row(str(i), n, c)
        console.print(f"\n[bold]'{keyword}' 검색 결과 {len(results)}건[/bold]\n")
        console.print(table)
        console.print("[yellow]번호를 입력하세요 (1~20):[/yellow] ", end="")
        try:
            idx = int(input().strip()) - 1
            if not (0 <= idx < min(len(results), 20)):
                raise ValueError
            name, code = results[idx]
        except (ValueError, IndexError):
            console.print("[red]잘못된 번호예요.[/red]")
            return

    stocks = load()
    if any(s["code"] == code for s in stocks):
        console.print(f"[yellow]{name} ({code}) 은 이미 워치리스트에 있어요.[/yellow]")
        return

    stocks.append({"name": name, "code": code})
    save(stocks)
    console.print(f"[green]✅ {name} ({code}) 추가됨[/green]")


def cmd_remove(keyword):
    stocks = load()
    if not stocks:
        console.print("[yellow]워치리스트가 비어 있어요.[/yellow]")
        return

    # 종목코드로 직접 삭제
    if keyword.isdigit() and len(keyword) == 6:
        target = [s for s in stocks if s["code"] == keyword]
        if not target:
            console.print(f"[red]{keyword} 은 워치리스트에 없어요.[/red]")
            return
        stocks = [s for s in stocks if s["code"] != keyword]
        save(stocks)
        console.print(f"[green]✅ {target[0]['name']} ({keyword}) 삭제됨[/green]")
        return

    # 이름으로 검색 후 삭제
    matches = [s for s in stocks if keyword in s["name"]]
    if not matches:
        console.print(f"[red]'{keyword}' 와 일치하는 종목이 워치리스트에 없어요.[/red]")
        return

    if len(matches) == 1:
        target = matches[0]
    else:
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        table.add_column("번호", justify="right", style="dim")
        table.add_column("회사명")
        table.add_column("종목코드")
        for i, s in enumerate(matches, 1):
            table.add_row(str(i), s["name"], s["code"])
        console.print(table)
        console.print("[yellow]번호를 입력하세요:[/yellow] ", end="")
        try:
            idx = int(input().strip()) - 1
            if not (0 <= idx < len(matches)):
                raise ValueError
            target = matches[idx]
        except (ValueError, IndexError):
            console.print("[red]잘못된 번호예요.[/red]")
            return

    stocks = [s for s in stocks if s["code"] != target["code"]]
    save(stocks)
    console.print(f"[green]✅ {target['name']} ({target['code']}) 삭제됨[/green]")


def main():
    if len(sys.argv) < 2:
        cmd_list()
        return

    cmd = sys.argv[1].lower()

    if cmd in ("list", "ls", "목록"):
        cmd_list()
    elif cmd in ("add", "추가"):
        if len(sys.argv) < 3:
            console.print("[yellow]사용법: python3 watchlist.py add 삼성전자[/yellow]")
            return
        cmd_add(" ".join(sys.argv[2:]))
    elif cmd in ("remove", "rm", "del", "삭제"):
        if len(sys.argv) < 3:
            console.print("[yellow]사용법: python3 watchlist.py remove 삼성전자[/yellow]")
            return
        cmd_remove(" ".join(sys.argv[2:]))
    else:
        console.print(f"[red]알 수 없는 명령: {cmd}[/red]")
        console.print("[dim]사용 가능: list / add <종목명> / remove <종목명>[/dim]")


if __name__ == "__main__":
    main()
