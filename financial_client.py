import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

CA_BUNDLE = os.getenv("REQUESTS_CA_BUNDLE")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://finance.naver.com",
}

# 테이블 행 순서 (네이버 금융 고정 구조)
ROW_MAP = {
    "매출액":     3,
    "영업이익":   4,
    "순이익":     5,
    "영업이익률": 6,
    "ROE":        8,
    "EPS":        12,
    "PER":        13,
    "PBR":        15,
    "배당수익률": 17,
}

def _parse(v: str):
    try:
        return float(v.replace(",", ""))
    except Exception:
        return None


def summarize_financials(fin: dict) -> list[tuple[str, str]]:
    """재무 수치를 해석해 (아이콘, 설명) 리스트 반환"""
    items = []

    per     = _parse(fin.get("PER", "-"))
    per_est = _parse(fin.get("PER_예상", "-"))
    pbr     = _parse(fin.get("PBR", "-"))
    roe     = _parse(fin.get("ROE", "-"))
    op_m    = _parse(fin.get("영업이익률", "-"))
    div     = _parse(fin.get("배당수익률", "-"))

    if per is not None:
        if per < 10:
            label = f"PER {per:.1f}배 — 코스피 평균 대비 저평가 구간"
            icon = "✅"
        elif per < 20:
            label = f"PER {per:.1f}배 — 적정 밸류에이션"
            icon = "✅"
        elif per < 30:
            label = f"PER {per:.1f}배 — 성장 기대감이 주가에 반영된 상태"
            icon = "⚠️ "
        else:
            label = f"PER {per:.1f}배 — 고평가, 실적이 기대에 부응해야 정당화"
            icon = "⚠️ "
        if per_est is not None and per > 0:
            if per_est > per * 1.03:
                label += f" (내년 예상 {per_est:.1f}배로 이익 성장이 주가를 못 따라가는 중)"
            elif per_est < per * 0.97:
                label += f" (내년 예상 {per_est:.1f}배 → 이익 성장 기대)"
        items.append((icon, label))

    if pbr is not None:
        if pbr < 1:
            items.append(("✅", f"PBR {pbr:.2f}배 — 장부 자산가치보다 싸게 거래 중"))
        elif pbr < 2:
            items.append(("✅", f"PBR {pbr:.2f}배 — 자산가치 대비 적정 수준"))
        elif pbr < 5:
            items.append(("⚠️ ", f"PBR {pbr:.2f}배 — 자산 대비 프리미엄 존재"))
        else:
            items.append(("⚠️ ", f"PBR {pbr:.2f}배 — 자산 대비 큰 프리미엄, 성장성이 핵심"))

    if roe is not None:
        if roe >= 20:
            items.append(("✅", f"ROE {roe:.1f}% — 자기자본 수익성 우수"))
        elif roe >= 10:
            items.append(("✅", f"ROE {roe:.1f}% — 수익성 양호"))
        elif roe >= 5:
            items.append(("❓", f"ROE {roe:.1f}% — 수익성 보통"))
        else:
            items.append(("⚠️ ", f"ROE {roe:.1f}% — 자본 효율성 낮음"))

    if op_m is not None:
        if op_m >= 15:
            items.append(("✅", f"영업이익률 {op_m:.1f}% — 매우 높은 수익 구조"))
        elif op_m >= 8:
            items.append(("✅", f"영업이익률 {op_m:.1f}% — 양호한 수익 구조"))
        elif op_m >= 3:
            items.append(("❓", f"영업이익률 {op_m:.1f}% — 보통 수준"))
        else:
            items.append(("⚠️ ", f"영업이익률 {op_m:.1f}% — 마진 낮음, 업종 특성 확인 필요"))

    if div is not None:
        if div < 0.5:
            items.append(("💡", f"배당수익률 {div:.2f}% — 배당 거의 없는 성장주 성격"))
        elif div < 2:
            items.append(("💡", f"배당수익률 {div:.1f}% — 소액 배당"))
        elif div < 4:
            items.append(("💡", f"배당수익률 {div:.1f}% — 안정적인 배당 수준"))
        else:
            items.append(("💡", f"배당수익률 {div:.1f}% — 고배당주"))

    return items


def get_financial_data(stock_code: str) -> dict:
    url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
    try:
        res = requests.get(url, headers=HEADERS, verify=CA_BUNDLE, timeout=10)
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "lxml")

        # PER 포함된 재무 테이블 찾기
        target_table = None
        for table in soup.select("table"):
            if "PER" in table.get_text():
                target_table = table
                break

        if not target_table:
            return {}

        rows = target_table.select("tr")
        # 연도 헤더는 rows[1]: ['2023.12', '2024.12', '2025.12', '2026.12(E)', ...]
        # rows[0]는 연간/분기 구분 헤더, rows[2]는 IFRS 표시 행
        year_row = [td.get_text(strip=True) for td in rows[1].select("th, td")]
        # 데이터 행의 col 0 = 항목명, col 1 = 2023.12, col 2 = 2024.12, col 3 = 2025.12, col 4 = 2026.12(E)
        recent_idx = 3   # 2025.12
        estimate_idx = 4 # 2026.12(E)

        def get_val(row_idx, col_idx):
            if row_idx >= len(rows):
                return "-"
            cells = [td.get_text(strip=True) for td in rows[row_idx].select("th, td")]
            if col_idx < len(cells):
                v = cells[col_idx]
                return v if v else "-"
            return "-"

        # year_row에는 항목명 열이 없으므로 인덱스를 1 감소시켜 참조
        recent_year = year_row[recent_idx - 1] if recent_idx - 1 < len(year_row) else "최근"
        estimate_year = year_row[estimate_idx - 1] if estimate_idx - 1 < len(year_row) else "예상"

        data = {
            "기준년도":  recent_year,
            "예상년도":  estimate_year,
            "매출액":    get_val(ROW_MAP["매출액"],     recent_idx),
            "영업이익":  get_val(ROW_MAP["영업이익"],   recent_idx),
            "영업이익률":get_val(ROW_MAP["영업이익률"], recent_idx),
            "순이익":    get_val(ROW_MAP["순이익"],     recent_idx),
            "ROE":       get_val(ROW_MAP["ROE"],         recent_idx),
            "EPS":       get_val(ROW_MAP["EPS"],         recent_idx),
            "PER":       get_val(ROW_MAP["PER"],         recent_idx),
            "PER_예상":  get_val(ROW_MAP["PER"],         estimate_idx),
            "PBR":       get_val(ROW_MAP["PBR"],         recent_idx),
            "배당수익률":get_val(ROW_MAP["배당수익률"],  recent_idx),
        }
        return data

    except Exception as e:
        return {}
