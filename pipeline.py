import os
import sys
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from watchlist import load as wl_load
from report import print_report
from blog_writer import process_report_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("pipeline.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

REPORTS_DIR = Path(__file__).parent / "reports"
BLOG_OUTPUT_DIR = Path(__file__).parent / "blog_output"
BLOG_OUTPUT_DIR.mkdir(exist_ok=True)


def upload_to_naver(title: str, content: str, chart_paths: dict) -> dict:
    from naver_client import post_article
    return post_article(title, content, chart_paths)


def run():
    start = datetime.now()
    logging.info("=" * 40)
    logging.info("파이프라인 시작")

    stocks = wl_load()
    if not stocks:
        logging.warning("워치리스트가 비어 있어요. 종료합니다.")
        sys.exit(1)

    # 커맨드라인 인자로 종목 필터링 (코드 또는 이름)
    filters = sys.argv[1:]
    if filters:
        stocks = [s for s in stocks if s["code"] in filters or s["name"] in filters]
        if not stocks:
            logging.warning(f"일치하는 종목 없음: {filters}")
            sys.exit(1)

    logging.info(f"대상 종목: {[s['name'] for s in stocks]}")

    results = []

    for s in stocks:
        code = s["code"]
        name = s["name"]

        # ── STEP 1: 데이터 수집 + MD 저장 + 차트 생성
        logging.info(f"[{name}] STEP 1 - 리포트 생성")
        try:
            chart_paths = print_report(code, name) or {}
        except Exception as e:
            logging.error(f"[{name}] 리포트 생성 실패: {e}")
            results.append({"name": name, "ok": False, "step": "report", "error": str(e)})
            continue

        # ── STEP 2: MD → HTML 변환 (Claude API)
        md_path = REPORTS_DIR / f"{name}_{code}.md"
        if not md_path.exists():
            logging.error(f"[{name}] MD 파일 없음: {md_path}")
            results.append({"name": name, "ok": False, "step": "blog_write", "error": "MD 파일 없음"})
            continue

        logging.info(f"[{name}] STEP 2 - 블로그 글 변환 (Claude API)")
        try:
            blog_data = process_report_file(str(md_path))
            logging.info(f"[{name}] 변환 완료: {blog_data['title']}")

            # 블로그 글 MD 파일로 저장
            today = datetime.now().strftime("%Y%m%d")
            blog_path = BLOG_OUTPUT_DIR / f"{today}_{name}_{code}.md"
            with open(blog_path, "w", encoding="utf-8") as f:
                f.write(f"# {blog_data['title']}\n\n")
                f.write(blog_data["content"])
            logging.info(f"[{name}] 블로그 글 저장: {blog_path}")
        except Exception as e:
            logging.error(f"[{name}] 블로그 글 변환 실패: {e}")
            results.append({"name": name, "ok": False, "step": "blog_write", "error": str(e)})
            continue

        # ── STEP 3: 네이버 블로그 업로드
        logging.info(f"[{name}] STEP 3 - 네이버 업로드")
        upload = upload_to_naver(blog_data["title"], blog_data["content"], chart_paths)

        results.append({
            "name": name,
            "title": blog_data["title"],
            "uploaded": upload["ok"],
        })

    # ── 최종 요약
    elapsed = int((datetime.now() - start).total_seconds())
    total = len(results)
    uploaded = sum(1 for r in results if r.get("uploaded"))
    failed = sum(1 for r in results if not r.get("uploaded") and "error" not in r)

    logging.info("=" * 40)
    logging.info(f"완료 ({elapsed}초) - 처리 {total}종목 | 업로드 {uploaded}건 | 스킵 {failed}건")

    errors = [r for r in results if "error" in r]
    if errors:
        for e in errors:
            logging.error(f"  실패: {e['name']} @ {e['step']} - {e['error']}")
        sys.exit(1)


if __name__ == "__main__":
    run()
