import sys
from rich.console import Console
from rich.table import Table
from rich import box
from dart_client import find_stock_code

console = Console()


def main():
    if len(sys.argv) < 2:
        console.print("[yellow]사용법: python3 lookup.py 삼성전자[/yellow]")
        sys.exit(1)

    keyword = sys.argv[1]
    results = find_stock_code(keyword)

    if not results:
        console.print(f"[red]'{keyword}' 와 일치하는 종목이 없어요.[/red]")
        console.print("[dim]줄임말 대신 정식 회사명으로 검색해보세요. (예: 현대차 → 현대자동차)[/dim]")
        sys.exit(1)

    if len(results) == 1:
        name, code = results[0]
        console.print(f"[green]✅ {name} → {code}[/green]")
        sys.exit(0)

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("번호", justify="right", style="dim")
    table.add_column("회사명")
    table.add_column("종목코드")

    for i, (name, code) in enumerate(results[:20], 1):
        table.add_row(str(i), name, code)

    console.print(f"\n[bold]'{keyword}' 검색 결과 {len(results)}건[/bold] (최대 20개 표시)\n")
    console.print(table)

    if len(results) > 20:
        console.print(f"[dim]... 외 {len(results) - 20}건. 더 구체적인 이름으로 검색해보세요.[/dim]")


if __name__ == "__main__":
    main()
