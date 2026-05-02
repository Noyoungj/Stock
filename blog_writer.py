import os
from pathlib import Path
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

RULES_FILE = Path(__file__).parent / "blog_rules.md"


def _load_rules() -> str:
    return RULES_FILE.read_text(encoding="utf-8")


def md_to_blog_html(md_content: str, stock_name: str, stock_code: str) -> dict:
    """MD 리포트를 받아 블로그용 HTML과 제목을 반환"""
    rules = _load_rules()

    system_prompt = f"""당신은 주식 장 마감 후, 오늘 하루를 정리해주는 블로그 작가입니다.
독자는 주식을 막 시작한 주린이(주식 초보자)입니다.

아래는 글쓰기 규칙입니다. 반드시 따라주세요.

{rules}
"""

    prompt = f"""아래는 오늘 장 마감 기준 {stock_name}({stock_code}) 데이터 리포트입니다.
이 내용을 바탕으로 네이버 블로그에 올릴 장 마감 정리 글을 작성해주세요.

**출력 형식 (반드시 지켜주세요):**
---TITLE---
(블로그 글 제목 한 줄)
---CONTENT---
(HTML 본문 내용)
---END---

제목 형식: "[종목명] 오늘 장 마감 정리 | YYYY.MM.DD"

---
{md_content}
---
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text

    if "---TITLE---" in raw and "---CONTENT---" in raw:
        title = raw.split("---TITLE---")[1].split("---CONTENT---")[0].strip()
        content = raw.split("---CONTENT---")[1].split("---END---")[0].strip()
    else:
        title = f"{stock_name} 오늘의 시황"
        content = f"<p>{raw}</p>"

    return {"title": title, "content": content}


def process_report_file(md_path: str) -> dict:
    """reports/ 폴더의 MD 파일 하나를 읽어 블로그 데이터 반환"""
    filename = os.path.basename(md_path)
    parts = filename.replace(".md", "").rsplit("_", 1)
    stock_name = parts[0] if len(parts) == 2 else filename
    stock_code = parts[1] if len(parts) == 2 else ""

    with open(md_path, encoding="utf-8") as f:
        md_content = f.read()

    result = md_to_blog_html(md_content, stock_name, stock_code)
    result["stock_name"] = stock_name
    result["stock_code"] = stock_code
    return result
