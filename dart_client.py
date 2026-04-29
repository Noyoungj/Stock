import os
import io
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("DART_API_KEY")
CA_BUNDLE = os.getenv("REQUESTS_CA_BUNDLE")
BASE_URL = "https://opendart.fss.or.kr/api"

_corp_map  = {}  # 종목코드 -> corp_code
_name_map  = {}  # 회사명   -> stock_code

def _load_corp_map():
    global _corp_map, _name_map
    if _corp_map:
        return

    url = f"{BASE_URL}/corpCode.xml"
    res = requests.get(url, params={"crtfc_key": API_KEY}, verify=CA_BUNDLE, timeout=30)
    res.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        with z.open("CORPCODE.xml") as f:
            tree = ET.parse(f)

    for item in tree.getroot().findall("list"):
        stock_code = item.findtext("stock_code", "").strip()
        corp_code  = item.findtext("corp_code",  "").strip()
        corp_name  = item.findtext("corp_name",  "").strip()
        if stock_code:
            _corp_map[stock_code] = corp_code
            _name_map[corp_name]  = stock_code


def find_stock_code(keyword: str) -> list[tuple[str, str]]:
    """종목명 키워드로 (회사명, 종목코드) 목록 반환 (상장 종목만)"""
    _load_corp_map()
    keyword = keyword.strip()
    results = []
    for name, code in _name_map.items():
        if keyword in name:
            results.append((name, code))
    results.sort(key=lambda x: (not x[0].startswith(keyword), len(x[0])))
    return results


def find_name_by_code(stock_code: str) -> str | None:
    """종목코드로 회사명 반환 (없으면 None)"""
    _load_corp_map()
    for name, code in _name_map.items():
        if code == stock_code:
            return name
    return None

def get_disclosures(stock_code, days=14):
    _load_corp_map()

    corp_code = _corp_map.get(stock_code)
    if not corp_code:
        return []

    end_de = datetime.today().strftime("%Y%m%d")
    bgn_de = (datetime.today() - timedelta(days=days)).strftime("%Y%m%d")

    res = requests.get(
        f"{BASE_URL}/list.json",
        params={
            "crtfc_key": API_KEY,
            "corp_code": corp_code,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "page_count": 10,
        },
        verify=CA_BUNDLE,
        timeout=15,
    )
    res.raise_for_status()
    data = res.json()

    if data.get("status") != "000":
        return []

    results = []
    for item in data.get("list", []):
        results.append({
            "date": item.get("rcept_dt", ""),
            "title": item.get("report_nm", ""),
            "submitter": item.get("flr_nm", ""),
            "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item.get('rcept_no','')}",
        })
    return results
