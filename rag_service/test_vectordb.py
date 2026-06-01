# -*- coding: utf-8 -*-
"""
벡터DB RAG 검증 테스트 (데이터 비의존 — 실제 적재된 데이터에서 값 추출).
사전조건: store/ 생성 (python ingest.py)
실행: python test_vectordb.py
"""
import os
import sys

from rag_vectordb import RagService, VectorRetriever, REFUSAL_MSG

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  [PASS] {name}")
    else:
        FAIL += 1; print(f"  [FAIL] {name}  {detail}")


def _sample(df):
    """가장 리뷰가 많은 과목과, 그 과목의 한 교수를 반환(데이터 비의존)."""
    reviews = df[df["source"] == "review"] if "source" in df.columns else df
    course = reviews["course"].value_counts().index[0]
    prof = reviews[reviews["course"] == course]["professor"].value_counts().index[0]
    return course, prof


def test_store_loaded():
    print("\n[저장소] 적재 확인")
    r = VectorRetriever()
    check("리뷰 적재됨(>0)", r.store.count() > 0, f"{r.store.count()}건")
    check("임베딩 차원 일치", r.store.vectors.shape[1] == r.store.dim, str(r.store.vectors.shape))
    n_course = r.store.rows["course"].nunique()
    print(f"  과목 수: {n_course}, 총 {r.store.count()}건")
    check("과목이 존재", n_course >= 1)


def test_3_1_semantic():
    print("\n[3.1] 벡터 의미 검색 top-k")
    r = VectorRetriever()
    res = r.retrieve("과제 적고 학점 잘 주는 꿀강", top_k=5)
    check("top-k 반환", len(res) >= 1)
    check("유사도 내림차순", all(res[i].score >= res[i+1].score for i in range(len(res)-1)))


def test_3_2_filter():
    print("\n[3.2] 교수/과목 속성 필터")
    r = VectorRetriever()
    course, prof = _sample(r.store.rows)
    print(f"  표본: 과목='{course}', 교수='{prof}'")
    res = r.retrieve("이 수업 어때", course=course, top_k=5)
    check("과목 필터 결과 존재", len(res) > 0)
    check("과목 필터 정확", all(course.replace(" ", "") in x.course.replace(" ", "") for x in res))
    res2 = r.retrieve("이 교수 어때", professor=prof, top_k=5)
    check("교수 필터 정확", res2 and all(prof in x.professor for x in res2))


def test_3_3_citation():
    print("\n[3.3] 출처 표기 (학교/과목/학기/평점)")
    r = VectorRetriever()
    rev = r.retrieve("꿀강", top_k=1)[0]
    c = rev.citation()
    check("학교 포함", rev.school in c, c)
    check("평점 포함", f"평점 {rev.rating}점" in c, c)
    check("리뷰 참고 형식", c.endswith("리뷰 참고)"), c)
    print(f"  예시 출처: {c}")


def test_3_4_refusal():
    print("\n[3.4] 환각 방지 / 답변 거부")
    svc = RagService(llm="offline")
    out = svc.answer("이 교수 어때요", professor="절대없는교수이름999")
    check("없는 교수 -> 거부", out["answer"] == REFUSAL_MSG and out["grounded"] is False, out["answer"])
    out2 = svc.answer("이 과목 꿀강?", course="존재하지않는과목XYZ")
    check("없는 과목 -> 거부", out2["answer"] == REFUSAL_MSG, out2["answer"])
    course, _ = _sample(VectorRetriever().store.rows)
    out3 = svc.answer("이 과목 꿀강?", course=course)
    check("있는 과목 -> 정상 답변", out3["grounded"] is True)


def test_llm_backend():
    print("\n[LLM 백엔드] 선택 로직")
    off = RagService(llm="offline")
    check("offline 강제 동작", off.llm == "offline")
    auto = RagService(llm="auto")
    expected = "claude" if os.environ.get("ANTHROPIC_API_KEY") else (
        "gemini" if os.environ.get("GEMINI_API_KEY") else "offline")
    check(f"auto → {expected}", auto.llm == expected, auto.llm)


def demo_real():
    print("\n[데모] 실제 과목 질의")
    r = VectorRetriever()
    course, _ = _sample(r.store.rows)
    svc = RagService(llm="offline")
    out = svc.answer(f"{course} 학점 잘 주는 교수 추천", course=course, top_k=4)
    print(f"\n--- '{course}' 질의 답변 ---")
    print(out["answer"])
    for s in out["sources"]:
        print(f"  · {s['professor']} {s['citation']} sim={s['score']}")


def main():
    print("=" * 60)
    print("에타 강의평 벡터DB RAG 테스트 (실제 크롤링 데이터)")
    print("임베딩:", "Gemini" if os.environ.get("GEMINI_API_KEY") else "LSA(오프라인)")
    print("LLM:", "claude" if os.environ.get("ANTHROPIC_API_KEY") else
          ("gemini" if os.environ.get("GEMINI_API_KEY") else "offline"))
    print("=" * 60)
    test_store_loaded()
    test_3_1_semantic()
    test_3_2_filter()
    test_3_3_citation()
    test_3_4_refusal()
    test_llm_backend()
    demo_real()
    print("\n" + "=" * 60)
    print(f"결과: {PASS} PASSED, {FAIL} FAILED")
    print("=" * 60)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
