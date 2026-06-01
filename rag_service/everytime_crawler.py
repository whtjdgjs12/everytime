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
import os
import sys
import time

from ev_parse import width_to_stars, text_to_stars, clean_review_text, course_matches

HERE = os.path.dirname(os.path.abspath(__file__))
DEBUG_DIR = os.path.join(HERE, "debug")
OUT_DEFAULT = os.path.join(HERE, "reviews_real.csv")

LOGIN_URL = "https://everytime.kr/login"
LECTURE_URL = "https://everytime.kr/lecture"

TARGET_COURSES = [
    "확률과 통계",
    "모바일프로그래밍",
    "빅데이터분석개론",
    "스마트기기시스템",
    "블록체인개론",
]

# ─────────────────────────────────────────────────────────────────────────────
# 셀렉터: 에타 DOM 변경/학교별 차이로 안 맞을 수 있다. debug/ 덤프를 보고 수정하라.
# ─────────────────────────────────────────────────────────────────────────────
SELECTORS = {
    "login_id":     "input[name='id'], input[name='userid']",
    "login_pw":     "input[name='password']",
    "login_submit": "input[type='submit'], button[type='submit'], .submit input",
    "login_done":   "#submenu, .myinfo, a[href*='logout']",   # 로그인 성공 표식

    "search_input": "input[name='keyword'], input[type='search'], .search input",
    "result_item":  ".lecture, .result .lecture, #result .lectures > *",
    "result_name":  ".name, .lecture_name, h3",
    "result_prof":  ".professor, .prof",

    "review_item":  ".article, .review, .articles > *",
    "review_text":  ".text, .article_text, p",
    "review_star":  ".star .on, .stars .on, .rate .on, .star",   # 채워진 별/너비
    "review_score": ".rate, .score, .star_score",                # 숫자 평점(있으면)
    "more_button":  ".more, .button.more, a.more",               # 더보기(있으면)
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


def login(page, ev_id: str, ev_pw: str) -> bool:
    log("로그인 페이지 이동")
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    idl = _first_present(page, SELECTORS["login_id"])
    pwl = _first_present(page, SELECTORS["login_pw"])
    if not idl or not pwl:
        capture(page, "login_form_not_found")
        log("로그인 폼을 찾지 못함 → debug 캡처 참고")
        return False
    idl.first.fill(ev_id)
    pwl.first.fill(ev_pw)
    sub = _first_present(page, SELECTORS["login_submit"])
    if sub:
        sub.first.click()
    else:
        pwl.first.press("Enter")
    page.wait_for_timeout(3000)
    if _first_present(page, SELECTORS["login_done"]):
        log("로그인 성공 추정")
        return True
    capture(page, "login_result")
    log("로그인 성공 표식 미확인 → debug 캡처 확인(캡차/비번 오류 가능)")
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


def extract_reviews_from_page(page, course: str, professor: str, school: str) -> list[dict]:
    """현재 강의 상세 페이지에서 강의평 목록을 추출. (오프라인 테스트 대상 함수)"""
    items = _first_present(page, SELECTORS["review_item"])
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
        rows.append({
            "school": school,
            "professor": professor or "미상",
            "course": course,
            "rating": extract_rating(item),
            "review": text,
            "source": "review",
        })
    return rows


def search_and_collect(page, course: str, school: str, delay: float) -> list[dict]:
    log(f"과목 검색: {course}")
    page.goto(LECTURE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(int(delay * 1000))
    box = _first_present(page, SELECTORS["search_input"])
    if not box:
        capture(page, f"search_box_not_found_{course}")
        return []
    box.first.fill(course)
    box.first.press("Enter")
    page.wait_for_timeout(int(delay * 1000))

    results = _first_present(page, SELECTORS["result_item"])
    if not results:
        capture(page, f"no_results_{course}")
        return []

    collected: list[dict] = []
    count = results.count()
    log(f"  검색 결과 {count}건 — 일치 강의 탐색")
    for i in range(count):
        item = results.nth(i)
        name_loc = _first_present(item, SELECTORS["result_name"])
        name = ""
        try:
            name = name_loc.first.inner_text() if name_loc else item.inner_text()
        except Exception:
            pass
        if not course_matches(course, name):
            continue
        prof_loc = _first_present(item, SELECTORS["result_prof"])
        professor = ""
        try:
            professor = prof_loc.first.inner_text().strip() if prof_loc else ""
        except Exception:
            pass
        try:
            item.click()
            page.wait_for_timeout(int(delay * 1000))
        except Exception as e:
            log(f"  강의 클릭 실패: {e}")
            capture(page, f"click_fail_{course}_{i}")
            continue
        rows = extract_reviews_from_page(page, course, professor, school)
        log(f"  '{name.strip()[:20]}' ({professor}) → 리뷰 {len(rows)}건")
        collected.extend(rows)
        page.go_back(wait_until="domcontentloaded")
        page.wait_for_timeout(int(delay * 1000))
    return collected


def crawl(courses, school, out_path, headless, delay) -> int:
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
                all_rows.extend(search_and_collect(page, c, school, delay))
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
    cols = ["id", "school", "professor", "course", "rating", "review", "source"]
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
    args = ap.parse_args()

    log("대상 과목: " + ", ".join(args.courses))
    log("⚠️ 자동 수집은 에타 약관 위반·계정 정지 위험이 있으며 실행 책임은 본인에게 있습니다.")
    rc = crawl(args.courses, args.school, args.out, args.headless, args.delay)
    sys.exit(rc)


if __name__ == "__main__":
    main()
