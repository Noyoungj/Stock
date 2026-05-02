import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

CHARTS_DIR = Path(__file__).parent / "charts"
CHARTS_DIR.mkdir(exist_ok=True)

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False


def generate_charts(code: str, name: str, df, fin: dict) -> dict:
    """차트 생성 후 경로 dict 반환"""
    paths = {}
    paths["price"] = _price_chart(code, name, df)
    paths["volume"] = _volume_chart(code, name, df)
    paths["volume_table"] = _volume_table_chart(code, name, df)
    if fin:
        p = _financial_chart(code, name, fin)
        if p:
            paths["financial"] = p
        p2 = _financial_table_chart(code, name, fin)
        if p2:
            paths["financial_table"] = p2
    return paths


def _price_chart(code: str, name: str, df) -> str:
    periods = [
        ("1년",  df,            mdates.MonthLocator(),              mdates.DateFormatter("%y/%m")),
        ("1개월", df.tail(22),  mdates.WeekdayLocator(interval=1),  mdates.DateFormatter("%m/%d")),
        ("1주일", df.tail(5),   mdates.DayLocator(),                mdates.DateFormatter("%m/%d")),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    fig.suptitle(f"{name} 주가 추이", fontsize=14, fontweight="bold", y=1.02)

    for ax, (label, data, locator, formatter) in zip(axes, periods):
        ax.plot(data.index, data["Close"], color="#e74c3c", linewidth=2)
        ax.fill_between(data.index, data["Close"], data["Close"].min() * 0.99,
                        alpha=0.1, color="#e74c3c")
        ax.set_title(label, fontsize=12)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(x):,}"))
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(formatter)
        ax.tick_params(axis="x", rotation=30)
        ax.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    path = str(CHARTS_DIR / f"{name}_{code}_price.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def _volume_chart(code: str, name: str, df) -> str:
    fig, ax = plt.subplots(figsize=(10, 3))
    colors = ["#e74c3c" if c >= 0 else "#3498db" for c in df["Change"]]
    ax.bar(df.index, df["Volume"], color=colors, alpha=0.85, width=0.8)
    ax.set_title(f"{name} 거래량  (빨강=상승일 / 파랑=하락일)", fontsize=13, fontweight="bold", pad=12)
    ax.set_ylabel("거래량")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(x/10000):,}만"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    fig.autofmt_xdate()
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    path = str(CHARTS_DIR / f"{name}_{code}_volume.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _volume_table_chart(code: str, name: str, df) -> str:
    recent = df.tail(5).copy()
    avg_20 = df["Volume"].tail(20).mean()

    table_data = []
    cell_colors = []

    for idx, row in recent.iterrows():
        vol = int(row["Volume"])
        ratio = vol / avg_20 if avg_20 > 0 else 1.0
        date_str = idx.strftime("%m/%d")
        vol_str = f"{vol / 10000:.0f}만 주"

        if ratio >= 2.0:
            label = f"{ratio:.1f}배 🔥"
            bg = "#ffcdd2"
        elif ratio >= 1.5:
            label = f"{ratio:.1f}배 ↑"
            bg = "#ffe0b2"
        elif ratio <= 0.7:
            label = f"{ratio:.1f}배 ↓"
            bg = "#e8f5e9"
        else:
            label = "정상"
            bg = "#ffffff"

        table_data.append([date_str, vol_str, label])
        cell_colors.append(["#f5f5f5", "#f9f9f9", bg])

    col_labels = ["날짜", "거래량", "평소 대비"]
    col_colors = ["#37474f"] * 3

    fig, ax = plt.subplots(figsize=(7, 2.4))
    ax.axis("off")

    tbl = ax.table(
        cellText=table_data,
        colLabels=col_labels,
        cellColours=cell_colors,
        colColours=col_colors,
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(11)
    tbl.scale(1, 1.9)

    for j in range(len(col_labels)):
        tbl[0, j].set_text_props(color="white", fontweight="bold")

    for i in range(1, len(table_data) + 1):
        for j in range(len(col_labels)):
            tbl[i, j].set_edgecolor("#e0e0e0")

    ax.set_title(f"{name} — 최근 5일 거래량", fontsize=12, fontweight="bold",
                 pad=12, color="#263238")

    plt.tight_layout()
    path = str(CHARTS_DIR / f"{name}_{code}_volume_table.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _financial_table_chart(code: str, name: str, fin: dict) -> str:
    def _parse(v):
        try:
            return float(str(v).replace(",", ""))
        except (ValueError, TypeError):
            return None

    metrics = [
        ("PER (배)",       "PER",       "PER_예상"),
        ("PBR (배)",       "PBR",       None),
        ("ROE (%)",        "ROE",       None),
        ("영업이익률 (%)",  "영업이익률", None),
    ]

    def _meaning(key, v):
        if v is None:
            return "-"
        if key == "PER":
            return f"1년치 이익의 {v:.1f}배 가격 — 연 1억 버는 가게를 {v:.0f}억에 사는 것"
        if key == "PBR":
            suffix = " (자산보다 싸게 사는 것)" if v < 1 else ""
            return f"순자산의 {v:.1f}배 가격{suffix}"
        if key == "ROE":
            suffix = " ✅ 우량" if v >= 10 else ""
            return f"주주 돈 100원으로 {v:.1f}원 벌음{suffix}"
        if key == "영업이익률":
            suffix = " ✅ 탄탄" if v >= 10 else ""
            return f"100원 팔면 {v:.1f}원이 진짜 이익{suffix}"
        return "-"

    rows, cell_colors = [], []
    for label, key, est_key in metrics:
        raw = fin.get(key, "-")
        v = _parse(raw)
        val_str = f"{raw}" if raw != "-" else "-"
        if est_key and fin.get(est_key, "-") != "-":
            val_str += f" (예상 {fin.get(est_key)})"
        rows.append([label, val_str, _meaning(key, v)])
        cell_colors.append(["#eceff1", "#f9f9f9", "#ffffff"])

    if not rows:
        return ""

    col_labels = ["지표", "값", "의미"]
    col_widths = [0.18, 0.22, 0.60]

    fig, ax = plt.subplots(figsize=(13, 3.0))
    ax.axis("off")

    tbl = ax.table(
        cellText=rows,
        colLabels=col_labels,
        cellColours=cell_colors,
        colColours=["#37474f"] * 3,
        colWidths=col_widths,
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1, 2.1)

    for j in range(len(col_labels)):
        tbl[0, j].set_text_props(color="white", fontweight="bold")
    for i in range(1, len(rows) + 1):
        tbl[i, 2].set_text_props(ha="left")
        for j in range(len(col_labels)):
            tbl[i, j].set_edgecolor("#e0e0e0")

    ax.set_title(f"{name} — 재무 지표 해설", fontsize=12, fontweight="bold",
                 pad=12, color="#263238")
    plt.tight_layout()
    path = str(CHARTS_DIR / f"{name}_{code}_financial_table.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _financial_chart(code: str, name: str, fin: dict) -> str:
    labels, values = [], []
    for key in ["매출액", "영업이익", "순이익"]:
        v = fin.get(key)
        if v and v != "-":
            try:
                labels.append(key)
                values.append(float(str(v).replace(",", "")))
            except ValueError:
                pass
    if not values:
        return ""

    fig, ax = plt.subplots(figsize=(7, 4))
    palette = ["#3498db", "#2ecc71", "#9b59b6"]
    bars = ax.bar(labels, values, color=palette[: len(labels)], alpha=0.85)
    ax.set_title(f"{name} 주요 재무지표 (억원)", fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel("금액 (억원)")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(x):,}"))
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() * 1.02,
            f"{int(val):,}",
            ha="center", va="bottom", fontsize=10,
        )
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    path = str(CHARTS_DIR / f"{name}_{code}_financial.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
