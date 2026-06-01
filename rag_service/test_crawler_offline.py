# -*- coding: utf-8 -*-
"""
크롤러 오프라인 검증 (에타 접속 없이 — 파싱/평점/CSV/캡처폴백/파이프라인 연동).
실제 로그인 크롤은 사용자가 직접 실행한다. 여기서는 네트워크 없는 모든 로직을 검증.
실행: python test_crawler_offline.py
"""
import os
import sys

import pandas as pd

from ev_parse import width_to_stars, text_to_stars, clean_review_text, course_matches
import everytime_crawler as ec

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  [PASS] {name}")
    else:
        FAIL += 1; print(f"  [FAIL] {name}  {detail}")


# 에타 강의 상세 페이지의 강의평 구조(article > p[별점]/p[학기]/p[본문])와 동일한 픽스처
FIXTURE_HTML = """
<html><body>
<div id="container"><div class="side"></div><div class="pane">
  <article>
     <p class="rate"><span><span style="width: 100%"></span></span></p>
     <p class="semester"><span>2024년 1학기</span></p>
     <p class="text">교수님 설명이 깔끔하고 시험도 족보 위주라 학점 잘 나옴 꿀강 인정</p>
  </article>
  <article>
     <p class="rate"><span><span style="width: 40%"></span></span></p>
     <p class="semester"><span>2023년 2학기</span></p>
     <p class="text">과제 폭탄에 팀플 헬이라 진짜 힘들었음 비추</p>
  </article>
  <article>
     <p class="rate"><span><span style="width: 60%"></span></span></p>
     <p class="semester"><span>2024년 1학기</span></p>
     <p class="text">ok</p>   <!-- 5자 미만 → 제외되어야 함 -->
  </article>
</div></div>
</body></html>
"""


def test_pure_parsers():
    print("\n[순수 파서] ev_parse")
    check("width 100% → 5점", width_to_stars("width: 100%") == 5)
    check("width 40% → 2점", width_to_stars("width:40%") == 2)
    check("width 90% → 4(반올림)", width_to_stars("width: 90%") == 4)
    check("text '4.0' → 4점", text_to_stars("평점 4.0") == 4)
    check("공백 정제", clean_review_text("  여러   줄\n공백 ") == "여러 줄 공백")
    check("과목명 공백무시 매칭", course_matches("확률과 통계", "확률과통계"))
    check("다른 과목 불일치", not course_matches("블록체인개론", "운영체제"))
    check("외국인반 제외", ec.is_excluded("확률과 통계 (외국인반)"))
    check("공학인증 제외", ec.is_excluded("모바일프로그래밍 공학인증"))
    check("영어강의 제외", ec.is_excluded("빅데이터분석개론 영어강의"))
    check("일반강의 통과", not ec.is_excluded("블록체인개론 김교수"))


def test_extract_from_dom():
    print("\n[DOM 추출] extract_reviews_from_page (Playwright set_content)")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content(FIXTURE_HTML)
        rows = ec.extract_reviews_from_page(page, "확률과 통계", "홍길동", "우리학교")
        # 캡처 폴백도 함께 검증
        ec.capture(page, "offline_test_capture")
        b.close()

    check("리뷰 2건 추출(짧은 1건 제외)", len(rows) == 2, f"{len(rows)}건")
    check("평점 정확(5,2)", [r["rating"] for r in rows] == [5, 2], str([r["rating"] for r in rows]))
    check("수강학기 추출", [r["semester"] for r in rows] == ["2024년 1학기", "2023년 2학기"],
          str([r.get("semester") for r in rows]))
    check("교수/과목/소스 채움",
          rows[0]["professor"] == "홍길동" and rows[0]["course"] == "확률과 통계"
          and rows[0]["source"] == "review")
    check("본문 정제됨", "꿀강" in rows[0]["review"])
    check("캡처 png 생성", os.path.exists(os.path.join(ec.DEBUG_DIR, "offline_test_capture.png")))
    check("DOM 덤프 html 생성", os.path.exists(os.path.join(ec.DEBUG_DIR, "offline_test_capture.html")))

    # 강의당 최대 개수 제한 검증
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(); page.set_content(FIXTURE_HTML)
        limited = ec.extract_reviews_from_page(page, "확률과 통계", "홍길동", "우리학교", limit=1)
        b.close()
    check("limit=1 → 1건만 수집", len(limited) == 1, f"{len(limited)}건")
    return rows


def test_csv_and_pipeline(rows):
    print("\n[CSV/파이프라인] 출력 스키마 ↔ ingest 연동")
    out = os.path.join(ec.HERE, "reviews_crawled_test.csv")
    ec.write_rows(rows, out)
    df = pd.read_csv(out)
    import ingest
    check("컬럼이 ingest 통합 스키마와 일치", list(df.columns) == ingest.COLUMNS, str(list(df.columns)))
    check("id 1부터 부여", df["id"].tolist() == [1, 2])
    check("rating 정수형", str(df["rating"].dtype).startswith("int"))
    check("source 모두 review", (df["source"] == "review").all())
    # ingest 의 doc_text 가 이 행으로 동작하는지(임베딩 입력 생성)
    txt = ingest.doc_text(df.iloc[0])
    check("doc_text 생성 가능", isinstance(txt, str) and len(txt) > 0)
    os.remove(out)


def main():
    print("=" * 60)
    print("에타 크롤러 오프라인 테스트 (네트워크/로그인 없음)")
    print("=" * 60)
    test_pure_parsers()
    rows = test_extract_from_dom()
    test_csv_and_pipeline(rows)
    print("\n" + "=" * 60)
    print(f"결과: {PASS} PASSED, {FAIL} FAILED")
    print("=" * 60)
    print("\n※ 실제 로그인 크롤(everytime_crawler.py)은 사용자가 직접 실행합니다.")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
