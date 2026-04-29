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

def get_news(stock_code: str, limit: int = 5) -> list:
    url = f"https://finance.naver.com/item/news_news.naver?code={stock_code}&page=1"

    try:
        res = requests.get(url, headers=HEADERS, verify=CA_BUNDLE, timeout=10)
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "lxml")

        results = []
        rows = soup.select("table.type5 tr")

        for row in rows:
            title_tag = row.select_one("td.title a")
            date_tag = row.select_one("td.date")
            source_tag = row.select_one("td.info")

            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            href = title_tag.get("href", "")
            link = f"https://finance.naver.com{href}" if href.startswith("/") else href
            date = date_tag.get_text(strip=True) if date_tag else ""
            source = source_tag.get_text(strip=True) if source_tag else ""

            if title:
                results.append({
                    "title": title,
                    "date": date,
                    "source": source,
                    "url": link,
                })

            if len(results) >= limit:
                break

        return results

    except Exception as e:
        return []
