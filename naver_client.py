import json
import os
import re
import random
import time
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

load_dotenv()

COOKIES_FILE = Path(__file__).parent / "naver_cookies.json"
BLOG_ID = os.getenv("NAVER_BLOG_ID", "")


def _extract_color(el) -> str | None:
    """인라인 style에서 color 값 추출"""
    style = el.get("style", "") if hasattr(el, "get") else ""
    m = re.search(r"color:\s*(#[0-9a-fA-F]{3,6})", style)
    return m.group(1) if m else None


def html_to_segments(html: str) -> list:
    """HTML을 세그먼트 리스트로 변환
    - ('text', [(text, is_bold, color), ...])   color는 None 또는 '#rrggbb'
    - ('table', [[셀, ...], ...])
    """
    segments = []
    text_buf = []  # (text, bold, color) 임시 버퍼

    def flush():
        if text_buf:
            segments.append(("text", list(text_buf)))
            text_buf.clear()

    def walk(el, bold=False, color=None):
        if isinstance(el, NavigableString):
            text = re.sub(r"\s+", " ", str(el))
            if text.strip():
                text_buf.append((text, bold, color))
            return
        tag = getattr(el, "name", None)
        if tag == "table":
            flush()
            rows = []
            for tr in el.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if rows:
                segments.append(("table", rows))
            return
        # 색상 span 처리
        el_color = _extract_color(el) or color
        if tag in ("h1", "h2", "h3"):
            text_buf.append(("\n", False, None))
            for c in el.children:
                walk(c, bold=True, color=el_color)
            text_buf.append(("\n", False, None))
        elif tag in ("p", "div"):
            for c in el.children:
                walk(c, bold, el_color)
            text_buf.append(("\n", False, None))
        elif tag in ("strong", "b"):
            for c in el.children:
                walk(c, bold=True, color=el_color)
        elif tag == "span":
            for c in el.children:
                walk(c, bold, el_color)
        elif tag == "li":
            text_buf.append(("• ", False, None))
            for c in el.children:
                walk(c, bold, el_color)
            text_buf.append(("\n", False, None))
        elif tag in ("ul", "ol"):
            for c in el.children:
                walk(c, bold, el_color)
        elif tag == "br":
            text_buf.append(("\n", False, None))
        elif tag == "a":
            href = el.get("href", "")
            link_parts = []
            def _link_collect(e):
                if isinstance(e, NavigableString):
                    t = re.sub(r"\s+", " ", str(e))
                    if t.strip():
                        link_parts.append(t)
                else:
                    for c in e.children:
                        _link_collect(c)
            _link_collect(el)
            link_text = "".join(link_parts).strip()
            if link_text and href:
                flush()
                segments.append(("link", link_text, href))
            elif link_text:
                text_buf.append((link_text, bold, color))
            return
        elif tag == "blockquote":
            flush()
            bq_parts = []
            def _bq_collect(e):
                if isinstance(e, NavigableString):
                    t = re.sub(r"\s+", " ", str(e))
                    if t.strip():
                        bq_parts.append(t)
                else:
                    for c in e.children:
                        _bq_collect(c)
            _bq_collect(el)
            bq_text = "".join(bq_parts).strip()
            if bq_text:
                segments.append(("blockquote", bq_text))
        elif tag:
            for c in el.children:
                walk(c, bold, el_color)

    soup = BeautifulSoup(html, "lxml")
    walk(soup)
    flush()
    return segments


def _insert_table(driver, rows: list):
    """SmartEditor ONE에 표 삽입. rows = [[셀, ...], ...]"""
    # 표 버튼 클릭 → 기본 3x3 생성
    table_btn = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, "//button[@data-name='table']"))
    )
    table_btn.click()
    time.sleep(2)

    # 가장 마지막에 생긴 표의 첫 번째 셀을 명시적으로 클릭
    try:
        all_cells = driver.find_elements(By.CSS_SELECTOR, "td.se-table-cell, th.se-table-cell")
        num_cells = len(rows) * len(rows[0])
        first_cell = all_cells[-num_cells]  # 마지막 표의 첫 셀
        first_cell.click()
        time.sleep(0.3)
    except Exception:
        pass

    # active_element로 직접 입력 → Tab으로 셀 이동
    for i, row in enumerate(rows):
        for j, cell_text in enumerate(row):
            cell = driver.switch_to.active_element
            cell.send_keys(str(cell_text))
            is_last = (i == len(rows) - 1 and j == len(row) - 1)
            if not is_last:
                cell.send_keys(Keys.TAB)
                time.sleep(0.15)

    # 표 밖으로 빠져나오기
    driver.switch_to.active_element.send_keys(Keys.ESCAPE)
    time.sleep(0.5)


def _type_by_actionchains(driver, element, text: str):
    """ActionChains로 1글자씩 0.01~0.10초 랜덤 딜레이 입력"""
    ac = ActionChains(driver)
    ac.click(element).perform()
    for ch in text:
        ActionChains(driver).send_keys(ch).perform()
        time.sleep(random.uniform(0.01, 0.10))


def _click_if_exists(driver, css_selector: str, timeout: int = 3):
    """셀렉터가 존재하면 클릭, 없으면 넘어감"""
    try:
        el = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, css_selector))
        )
        el.click()
        time.sleep(0.5)
    except Exception:
        pass


def _build_driver(headless: bool = False) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(options=opts)


def _load_cookies(driver):
    """저장된 쿠키를 드라이버에 주입"""
    if not COOKIES_FILE.exists():
        return
    cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
    for cookie in cookies:
        # Selenium은 sameSite 필드를 모름 — 제거
        cookie.pop("sameSite", None)
        try:
            driver.add_cookie(cookie)
        except Exception:
            pass


def _save_cookies(driver):
    cookies = driver.get_cookies()
    COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")


def _login(driver):
    print("\n[네이버 로그인] 브라우저에서 직접 로그인해주세요. (최대 2분)")
    driver.get("https://nid.naver.com/nidlogin.login")
    WebDriverWait(driver, 120).until(
        lambda d: "nidlogin" not in d.current_url
    )
    time.sleep(2)
    _save_cookies(driver)
    print("[네이버 로그인] 완료! 쿠키 저장됨.")


CHART_MARKERS = ["[CHART_PRICE]", "[CHART_VOLUME]", "[CHART_FINANCIAL]"]


def _upload_image(driver, abs_path: str):
    """스마트에디터 ONE에 이미지 업로드"""
    try:
        # 툴바의 사진 버튼 클릭
        img_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR,
                 "button.se-btn-toolbar-image, "
                 "button[data-name='image'], "
                 "button[title='사진']")
            )
        )
        img_btn.click()
        time.sleep(1.5)
    except Exception:
        return

    try:
        # 숨겨진 file input에 직접 경로 전달
        file_input = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
        )
        driver.execute_script("arguments[0].style.display='block';", file_input)
        file_input.send_keys(abs_path)
        time.sleep(4)  # 업로드 완료 대기
    except Exception:
        pass


def post_article(title: str, html_content: str, chart_paths: dict = None) -> dict:
    """네이버 블로그에 글 발행. 성공 시 {'ok': True, 'title': ...} 반환"""
    chart_paths = chart_paths or {}

    marker_key_map = {
        "[CHART_PRICE]": "price",
        "[CHART_VOLUME]": "volume",
        "[CHART_VOLUME_TABLE]": "volume_table",
        "[CHART_FINANCIAL_TABLE]": "financial_table",
        "[CHART_FINANCIAL]": "financial",
    }
    # 문서 순서대로 분할 (re.split으로 마커 위치 기준 순서 보장)
    pattern = "|".join(re.escape(m) for m in marker_key_map)
    raw_parts = re.split(f"({pattern})", html_content)
    segments = []
    i = 0
    while i < len(raw_parts):
        text = raw_parts[i].strip()
        i += 1
        chart_key = None
        if i < len(raw_parts) and raw_parts[i] in marker_key_map:
            chart_key = marker_key_map[raw_parts[i]]
            i += 1
        segments.append((text, chart_key))

    driver = _build_driver(headless=False)
    try:
        driver.get("https://blog.naver.com")
        time.sleep(1)
        _load_cookies(driver)

        write_url = f"https://blog.naver.com/{BLOG_ID}?Redirect=Write&"
        driver.get(write_url)
        time.sleep(3)

        if "nidlogin" in driver.current_url or "login" in driver.current_url:
            _login(driver)
            driver.get(write_url)
            time.sleep(3)

        WebDriverWait(driver, 15).until(
            EC.frame_to_be_available_and_switch_to_it((By.CSS_SELECTOR, "#mainFrame"))
        )
        time.sleep(1)

        _click_if_exists(driver, ".se-popup-button-cancel")
        _click_if_exists(driver, ".se-help-panel-close-button")

        # ── 제목 입력
        title_el = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-documentTitle"))
        )
        _type_by_actionchains(driver, title_el, title)

        # ── 본문: 텍스트 타이핑 (볼드는 Ctrl+B 토글) → 차트 업로드 반복
        body_el = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-text"))
        )
        body_el.click()
        time.sleep(0.5)

        def _toggle_bold():
            try:
                driver.find_element(
                    By.XPATH,
                    "//button[.//span[@class='se-blind' and text()='굵게']]"
                ).click()
            except Exception:
                ActionChains(driver).key_down(Keys.CONTROL).send_keys("b").key_up(Keys.CONTROL).perform()
            time.sleep(0.1)

        def _insert_link(text: str, url: str):
            # 링크 텍스트 입력
            for ch in text:
                ActionChains(driver).send_keys(ch).perform()
                time.sleep(random.uniform(0.01, 0.05))
            # 방금 입력한 텍스트 선택 (Shift+← * 글자수)
            for _ in range(len(text)):
                ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ARROW_LEFT).key_up(Keys.SHIFT).perform()
            time.sleep(0.2)
            # 링크 버튼 클릭
            try:
                driver.find_element(By.CSS_SELECTOR, "button[data-name='oglink']").click()
            except Exception:
                return
            time.sleep(1.5)
            # URL 입력창 찾기
            try:
                url_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input.se-popup-oglink-input"))
                )
                url_input.clear()
                url_input.send_keys(url)
                url_input.send_keys(Keys.RETURN)
                time.sleep(2)
            except Exception:
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                time.sleep(0.3)

        def _insert_blockquote(text: str):
            try:
                driver.find_element(
                    By.CSS_SELECTOR,
                    "button[data-name='quotation']"
                ).click()
            except Exception:
                pass
            time.sleep(0.2)
            for ch in text:
                ActionChains(driver).send_keys(ch).perform()
                time.sleep(random.uniform(0.01, 0.05))
            # 인용구 모드 종료 — 아래 화살표 두 번
            ActionChains(driver).send_keys(Keys.ARROW_DOWN).perform()
            time.sleep(0.1)
            ActionChains(driver).send_keys(Keys.ARROW_DOWN).perform()
            time.sleep(0.3)

        for html_seg, chart_key in segments:
            if html_seg:
                parsed = html_to_segments(html_seg)
                is_bold = False

                for seg in parsed:
                    if seg[0] == "table":
                        if is_bold:
                            _toggle_bold()
                            is_bold = False
                        _insert_table(driver, seg[1])
                        try:
                            body_el = driver.find_element(By.CSS_SELECTOR, ".se-section-text")
                            body_el.click()
                        except Exception:
                            pass
                    elif seg[0] == "blockquote":
                        if is_bold:
                            _toggle_bold()
                            is_bold = False
                        _insert_blockquote(seg[1])
                    elif seg[0] == "link":
                        if is_bold:
                            _toggle_bold()
                            is_bold = False
                        _insert_link(seg[1], seg[2])
                    else:
                        current_color = None
                        for text, bold, color in seg[1]:
                            if bold != is_bold:
                                _toggle_bold()
                                is_bold = bold
                            if color != current_color:
                                driver.execute_script(
                                    "document.execCommand('foreColor', false, arguments[0]);",
                                    color if color else "#000000"
                                )
                                current_color = color
                            for ch in text:
                                ActionChains(driver).send_keys(ch).perform()
                                time.sleep(random.uniform(0.01, 0.05))
                        if current_color:
                            driver.execute_script(
                                "document.execCommand('foreColor', false, '#000000');"
                            )

                if is_bold:
                    _toggle_bold()

            if chart_key and chart_key in chart_paths:
                _upload_image(driver, str(Path(chart_paths[chart_key]).resolve()))
                # 이미지 선택 해제 후 커서를 이미지 아래로 이동
                try:
                    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(0.3)
                    ActionChains(driver).send_keys(Keys.DOWN).perform()
                    time.sleep(0.2)
                    ActionChains(driver).send_keys(Keys.END).perform()
                    time.sleep(0.2)
                    ActionChains(driver).send_keys(Keys.RETURN).perform()
                    time.sleep(0.3)
                except Exception:
                    pass

        # ── 저장
        save_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".save_btn__bzc5B"))
        )
        save_btn.click()
        time.sleep(3)

        driver.switch_to.default_content()
        _save_cookies(driver)

        return {"ok": True, "title": title}

    except Exception as e:
        return {"ok": False, "error": str(e)}

    finally:
        driver.quit()
