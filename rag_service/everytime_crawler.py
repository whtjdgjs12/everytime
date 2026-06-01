# -*- coding: utf-8 -*-
"""
에브리타임 강의평 크롤러 (Playwright)
=====================================
지정한 5과목의 강의평을 수집해 reviews_real.csv 와 동일한 스키마로 저장한다.
수집 결과는 기존 RAG 파이프라인(ingest.py → rag_vectordb.py)에 그대로 투입된다.

⚠️ 주의 (반드시 읽을 것)
  - 에브리타임 약관은 자동 수집을 금지하며, 적발 시 계정 영구 정지/IP 차단 위험이 있다.
    이 스크립트의 실행 책임은 전적으로 실행자 본인에게 있다.
  - 계정 정보는 코드에 넣지 말고 환경변수로 전달한다:
        $env:EVERYTIME_ID="아이디"; $env:EVERYTIME_PW="비밀번호"
  - 기본은 headed(브라우저 보임) 모드다. 캡차/2단계 인증이 뜨면 직접 처리한다.
  - 과도한 요청은 차단을 부른다. 요청 간 지연(--delay)을 충분히 둔다.

셀렉터를 못 찾으면? → 자동으로 debug/ 에 스크린샷(.png)과 DOM 덤프(.html)를 남긴다.
그 파일을 열어 실제 구조를 보고 아래 SELECTORS 를 수정하면 된다.

실행:
  $env:EVERYTIME_ID="..."; $env:EVERYTIME_PW="..."
  python everytime_crawler.py                 # 5과목 기본 수집(headed)
  python everytime_crawler.py --headless       # 백그라운드
  python everytime_crawler.py --courses "확률과 통계" "블록체인개론"
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from urllib.parse import quote

from ev_parse import width_to_stars, text_to_stars, clean_review_text, course_matches

HERE = os.path.dirname(os.path.abspath(__file__))
DEBUG_DIR = os.path.join(HERE, "debug")
OUT_DEFAULT = os.path.join(HERE, "reviews_real.csv")

BASE = "https://everytime.kr"
LOGIN_URL = "https://everytime.kr/login"
SEARCH_URL = "https://everytime.kr/lecture/search?keyword={kw}&condition=name"

TARGET_COURSES = [
    "확률과 통계",
    "모바일프로그래밍",
    "빅데이터분석개론",
    "스마트기기시스템",
    "블록체인개론",
]

# 검색 결과에서 이 키워드가 강의명/표식에 있으면 제외 (외국인반/공학인증/영어강의)
EXCLUDE_KEYWORDS = [
    "외국인", "외국인반", "공학인증", "영어강의", "영어강좌",
    "(영어)", "[영어]", "English",
]

# ─────────────────────────────────────────────────────────────────────────────
# 셀렉터: 에타 DOM 변경/학교별 차이로 안 맞을 수 있다. debug/ 덤프를 보고 수정하라.
# ─────────────────────────────────────────────────────────────────────────────
# 참고: shkim0116/Lecture-Recommendation-NLP 및 에타 실제 구조 기반.
# 강의평은 <article> 태그, 별점은 내부 span 의 style width%(80%→4점), 본문은 p.text,
# 수강학기는 article 내 p > span 에 '2024년 1학기' 형태로 들어있다.
SELECTORS = {
    "login_id":     "input[name='id'], #container form p:nth-of-type(1) input",
    "login_pw":     "input[name='password'], #container form p:nth-of-type(2) input",
    "login_submit": "input[type='submit'], #container form p:last-of-type input, .submit input",
    "login_done":   "#submenu, .myinfo, a[href*='logout'], .profile",  # 로그인 성공 표식

    # 검색 결과는 /lecture/view/<id> 로 가는 링크들이다(직접 URL 이동에 사용).
    "result_link":  "a[href*='/lecture/view/']",
    "review_empty": "section.empty.review, .empty.review",   # '강의평 없음' 표식

    "review_item":  "article, .article, .pane article",
    "review_text":  "p.text, .text, article > p:nth-of-type(3), article p:last-of-type",
    # 별점: width% 를 가진 안쪽 span 우선
    "review_star":  "p span span[style*='width'], .star .on, .rate span span, .rate .on, .star",
    "review_score": ".rate.num, .score, .star_score",                  # 숫자 평점(있으면)
    "review_semester": "article > p:nth-of-type(2) span, .semester span, .semester",  # 수강학기
    "more_button":  ".more, .button.more, a.more",                     # 더보기(있으면)
}


def log(msg: str):
    print(f"[crawler] {msg}", flush=True)


def capture(page, label: str):
    """셀렉터 실패/디버깅용: 스크린샷 + 전체 DOM 덤프 저장."""
    os.makedirs(DEBUG_DIR, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:60]
    png = os.path.join(DEBUG_DIR, f"{safe}.png")
    html = os.path.join(DEBUG_DIR, f"{safe}.html")
    try:
        page.screenshot(path=png, full_page=True)
    except Exception as e:
        log(f"스크린샷 실패: {e}")
    try:
        with open(html, "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception as e:
        log(f"DOM 덤프 실패: {e}")
    log(f"⚠️ 캡처 저장 → {png} / {html}  (이 파일로 실제 DOM 확인 후 SELECTORS 수정)")


def _first_present(page_or_loc, selector: str):
    """콤마로 나열된 셀렉터 중 처음 존재하는 locator 반환(없으면 None)."""
    for sel in selector.split(","):
        sel = sel.strip()
        if not sel:
            continue
        loc = page_or_loc.locator(sel)
        try:
            if loc.count() > 0:
                return loc
        except Exception:
            continue
    return None


def wait_present(page, selector: str, timeout: int = 12000):
    """에타는 Vue SPA라 요소가 비동기 렌더된다. 셀렉터가 나타날 때까지 대기 후 locator 반환.
    (콤마 구분 셀렉터는 wait_for_selector 가 네이티브로 'OR' 처리한다.) 실패 시 None."""
    try:
        page.wait_for_selector(selector, timeout=timeout, state="attached")
        return _first_present(page, selector)
    except Exception:
        return None


def login(page, ev_id: str, ev_pw: str) -> bool:
    log("로그인 페이지 이동 (SPA 렌더 대기)")
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    # 에타 로그인은 account.everytime.kr 로 리다이렉트되며 Vue 로 폼이 비동기 렌더된다.
    idl = wait_present(page, SELECTORS["login_id"], timeout=15000)
    pwl = _first_present(page, SELECTORS["login_pw"])
    if not idl or not pwl:
        capture(page, "login_form_not_found")
        log("로그인 폼을 찾지 못함 → debug 캡처 참고 (렌더 지연/구조변경 가능)")
        return False
    idl.first.fill(ev_id)
    pwl.first.fill(ev_pw)
    sub = _first_present(page, SELECTORS["login_submit"])
    if sub:
        sub.first.click()
    else:
        pwl.first.press("Enter")
    # 제출 후 로그인 페이지를 벗어나거나 성공 표식이 뜰 때까지 대기
    try:
        page.wait_for_url(lambda u: "/login" not in u, timeout=12000)
    except Exception:
        pass
    page.wait_for_timeout(2500)
    if "/login" not in page.url or _first_present(page, SELECTORS["login_done"]):
        log(f"로그인 성공 추정 (현재 URL: {page.url})")
        return True
    capture(page, "login_result")
    log("로그인 성공 표식 미확인 → debug 캡처 확인 (reCAPTCHA/비번오류 가능)")
    return False


def extract_rating(item) -> int:
    """리뷰 1건의 평점 추출: ① 숫자 평점 텍스트 ② 별 width% ③ 채워진 별 개수."""
    score = _first_present(item, SELECTORS["review_score"])
    if score:
        try:
            v = text_to_stars(score.first.inner_text())
            if v:
                return v
        except Exception:
            pass
    star = _first_present(item, SELECTORS["review_star"])
    if star:
        try:
            style = star.first.get_attribute("style")
            v = width_to_stars(style)
            if v:
                return v
        except Exception:
            pass
        try:
            return max(0, min(5, star.count()))  # 채워진 별 개수 폴백
        except Exception:
            pass
    return 0


def is_excluded(text: str) -> bool:
    """외국인반/공학인증/영어강의 등 제외 대상인지."""
    t = str(text)
    return any(k in t for k in EXCLUDE_KEYWORDS)


def load_all_reviews(page, delay: float, target: int | None = None, max_rounds: int = 40) -> int:
    """에타 강의평은 무한 스크롤로 lazy-load 된다. 스크롤/더보기로 로드.
    target 개수가 차면 조기 종료(불필요한 스크롤·요청 방지)."""
    sel = SELECTORS["review_item"]
    prev = -1
    for _ in range(max_rounds):
        loc = _first_present(page, sel)
        cnt = loc.count() if loc else 0
        if target and cnt >= target:   # 필요한 만큼 모이면 그만
            return cnt
        if cnt == prev:
            more = _first_present(page, SELECTORS["more_button"])  # 더보기 버튼 있으면 클릭
            if more:
                try:
                    more.first.click()
                    page.wait_for_timeout(int(delay * 1000))
                    continue
                except Exception:
                    pass
            break
        prev = cnt
        try:
            if loc and cnt > 0:
                loc.nth(cnt - 1).scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        page.mouse.wheel(0, 5000)
        page.wait_for_timeout(int(delay * 800))
    return max(prev, 0)


def extract_reviews_from_page(page, course: str, professor: str, school: str,
                              limit: int | None = None) -> list[dict]:
    """현재 강의 상세 페이지에서 강의평 목록을 추출. limit 지정 시 그 개수까지만.
    (오프라인 테스트 대상 함수)"""
    items = wait_present(page, SELECTORS["review_item"], timeout=8000)
    if not items:
        capture(page, f"reviews_not_found_{course}")
        return []
    rows = []
    n = items.count()
    for i in range(n):
        item = items.nth(i)
        txt_loc = _first_present(item, SELECTORS["review_text"])
        try:
            raw = txt_loc.first.inner_text() if txt_loc else item.inner_text()
        except Exception:
            raw = ""
        text = clean_review_text(raw)
        if len(text) < 5:
            continue
        sem_loc = _first_present(item, SELECTORS["review_semester"])
        semester = ""
        try:
            if sem_loc:
                semester = clean_review_text(sem_loc.first.inner_text())
        except Exception:
            pass
        rows.append({
            "school": school,
            "professor": professor or "미상",
            "course": course,
            "semester": semester,
            "rating": extract_rating(item),
            "review": text,
            "source": "review",
        })
        if limit and len(rows) >= limit:   # 강의당 최대 개수 제한
            break
    return rows


def read_lecture_meta(page) -> tuple[str, str, str]:
    """상세 페이지의 __INITIAL_STATE__ JSON 에서 (과목명, 교수명, 학교명) 추출."""
    try:
        m = re.search(r'id="__INITIAL_STATE__"[^>]*>([^<]+)<', page.content())
        if m:
            from urllib.parse import unquote
            data = json.loads(unquote(m.group(1)))
            lec = data.get("lecture", {})
            school = data.get("campusData", {}).get("communityName", "")
            return lec.get("name", ""), lec.get("professor", ""), school
    except Exception:
        pass
    return "", "", ""


def _collect_lecture_urls(page, course: str) -> list[str]:
    """검색 결과에서 (과목 일치 & 비제외) 강의들의 강의평 탭 URL 목록을 수집."""
    links = wait_present(page, SELECTORS["result_link"], timeout=12000)
    if not links:
        capture(page, f"no_results_{course}")
        return []
    urls, seen = [], set()
    for i in range(links.count()):
        a = links.nth(i)
        try:
            href = a.get_attribute("href") or ""
            txt = a.inner_text()
        except Exception:
            continue
        if "/lecture/view/" not in href:
            continue
        if not course_matches(course, txt):
            continue
        if is_excluded(txt):
            log(f"  제외(외국인반/공학인증/영어강의): {txt.strip()[:24]}")
            continue
        base = href.split("?")[0]
        if base in seen:
            continue
        seen.add(base)
        full = base if base.startswith("http") else BASE + base
        urls.append(full + "?tab=article")   # 강의평 탭으로 직접 이동
    return urls


def search_and_collect(page, course: str, school: str, delay: float,
                       max_per_lecture: int = 10) -> list[dict]:
    log(f"과목 검색: {course}")
    # 1) 검색 페이지로 URL 직접 이동
    page.goto(SEARCH_URL.format(kw=quote(course)), wait_until="domcontentloaded")
    urls = _collect_lecture_urls(page, course)
    log(f"  대상 강의 {len(urls)}개 (과목 일치·제외 후)")

    # 2) 각 강의의 '강의평' 탭으로 직접 이동해 수집
    collected: list[dict] = []
    for url in urls:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(int(delay * 800))
        name, professor, school_detected = read_lecture_meta(page)
        sch = school_detected or school
        # 강의평 없음이면 조용히 건너뜀
        if _first_present(page, SELECTORS["review_empty"]) or \
                page.locator("text=아직 등록된 강의평이 없습니다").count() > 0:
            log(f"  '{(name or course)[:20]}' ({professor}) → 강의평 0개")
            continue
        loaded = load_all_reviews(page, delay, target=max_per_lecture)
        rows = extract_reviews_from_page(page, name or course, professor, sch, limit=max_per_lecture)
        log(f"  '{(name or course)[:20]}' ({professor}) → 로드 {loaded} / 수집 {len(rows)}건(최대 {max_per_lecture})")
        collected.extend(rows)
        time.sleep(delay)
    return collected


def crawl(courses, school, out_path, headless, delay, max_per_lecture=10) -> int:
    from playwright.sync_api import sync_playwright

    ev_id = os.environ.get("EVERYTIME_ID")
    ev_pw = os.environ.get("EVERYTIME_PW")
    if not ev_id or not ev_pw:
        log("환경변수 EVERYTIME_ID / EVERYTIME_PW 가 필요합니다.")
        log('  PowerShell:  $env:EVERYTIME_ID="아이디"; $env:EVERYTIME_PW="비밀번호"')
        return 1

    all_rows: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(locale="ko-KR")
        page = ctx.new_page()
        if not login(page, ev_id, ev_pw):
            log("로그인 실패 → 중단 (debug/ 확인)")
            browser.close()
            return 2
        for c in courses:
            try:
                all_rows.extend(search_and_collect(page, c, school, delay, max_per_lecture))
            except Exception as e:
                log(f"'{c}' 처리 중 오류: {e}")
                capture(page, f"error_{c}")
            time.sleep(delay)
        browser.close()

    if not all_rows:
        log("수집된 강의평이 없습니다. debug/ 의 캡처/덤프로 SELECTORS 를 점검하세요.")
        return 3

    write_rows(all_rows, out_path)
    log(f"완료: {len(all_rows)}건 저장 → {out_path}")
    log("다음 단계:  python ingest.py  &&  python rag_vectordb.py \"...\"")
    return 0


def write_rows(rows: list[dict], out_path: str):
    cols = ["id", "school", "professor", "course", "semester", "rating", "review", "source"]
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow({"id": i, **{k: r.get(k, "") for k in cols if k != "id"}})


def main():
    ap = argparse.ArgumentParser(description="에브리타임 강의평 크롤러")
    ap.add_argument("--courses", nargs="*", default=TARGET_COURSES, help="대상 과목명")
    ap.add_argument("--school", default="우리학교", help="school 컬럼 값")
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--headless", action="store_true", help="브라우저 숨김(기본: 보임)")
    ap.add_argument("--delay", type=float, default=2.0, help="요청 간 지연(초)")
    ap.add_argument("--max-per-lecture", type=int, default=10, dest="max_per_lecture",
                    help="강의당 최대 수집 리뷰 수(기본 10)")
    args = ap.parse_args()

    log("대상 과목: " + ", ".join(args.courses))
    log("⚠️ 자동 수집은 에타 약관 위반·계정 정지 위험이 있으며 실행 책임은 본인에게 있습니다.")
    rc = crawl(args.courses, args.school, args.out, args.headless, args.delay,
               args.max_per_lecture)
    sys.exit(rc)


if __name__ == "__main__":
    main()
