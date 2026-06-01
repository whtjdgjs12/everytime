# -*- coding: utf-8 -*-
"""
벡터DB RAG(실제 데이터) 검증 테스트.
사전조건: python build_dataset.py && python ingest.py  (store/ 생성)
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


def test_store_loaded():
    print("\n[저장소] 실제 데이터 적재 확인")
    r = VectorRetriever()
    df = r.store.rows
    n_review = int((df["source"] == "review").sum()) if "source" in df.columns else r.store.count()
    check("리뷰 995건 적재", n_review == 995, f"{n_review}건")
    check("임베딩 차원 일치", r.store.vectors.shape[1] == r.store.dim, str(r.store.vectors.shape))
    check("백엔드 표기", r.meta["backend"] in ("lsa", "gemini"), r.meta["backend"])


def test_syllabus():
    print("\n[강의계획서] PDF 벡터화 통합 확인")
    r = VectorRetriever()
    df = r.store.rows
    if "source" not in df.columns or (df["source"] == "syllabus").sum() == 0:
        check("강의계획서 적재(선택)", True, "syllabi.csv 없음 — 건너뜀")
        return
    n_syl = int((df["source"] == "syllabus").sum())
    check("강의계획서 청크 적재", n_syl > 0, f"{n_syl}청크")

    res = r.retrieve("강의계획서 평가 방법과 수업 목표", source="syllabus", top_k=3)
    check("syllabus 소스 검색 동작", len(res) > 0)
    check("결과가 모두 syllabus", all(x.source == "syllabus" for x in res))
    check("계획서 출처 표기", res and "강의계획서 참고)" in res[0].citation(), res[0].citation() if res else "")


def test_3_1_semantic():
    print("\n[3.1] 벡터 의미 검색 top-k")
    r = VectorRetriever()
    res = r.retrieve("과제 적고 학점 잘 주는 꿀강", top_k=5)
    check("top-5 반환", len(res) == 5, f"{len(res)}건")
    check("유사도 내림차순", all(res[i].score >= res[i+1].score for i in range(len(res)-1)))
    check("유사도 점수 존재(>0)", res[0].score > 0, str(res[0].score))


def test_3_2_filter():
    print("\n[3.2] 교수/과목 속성 필터")
    r = VectorRetriever()
    res = r.retrieve("이 수업 어때요", professor="윤승태", top_k=5)
    check("교수 필터 결과 존재", len(res) > 0)
    check("교수 필터 정확", all("윤승태" in x.professor for x in res))

    res2 = r.retrieve("꿀강 추천", course="컴퓨터프로그래밍", top_k=5)
    check("과목 필터 결과 존재", len(res2) > 0)
    check("과목 필터 정확", all("컴퓨터프로그래밍" in x.course for x in res2))


def test_3_3_citation():
    print("\n[3.3] 출처 표기 (학교/과목/평점)")
    r = VectorRetriever()
    rev = r.retrieve("꿀강", top_k=1)[0]
    c = rev.citation()
    check("학교 포함", rev.school in c, c)
    check("평점 포함", f"평점 {rev.rating}점" in c, c)
    check("리뷰 참고 형식", c.endswith("리뷰 참고)"), c)

    out = RagService().answer("컴퓨터프로그래밍 꿀강", course="컴퓨터프로그래밍")
    check("답변에 출처 괄호 표기", "리뷰 참고)" in out["answer"], out["answer"][:80])
    check("sources 반환", len(out["sources"]) > 0)


def test_3_4_refusal():
    print("\n[3.4] 환각 방지 / 답변 거부")
    svc = RagService()
    out = svc.answer("이 교수 어때요", professor="절대없는교수이름999")
    check("없는 교수 -> 거부", out["answer"] == REFUSAL_MSG and out["grounded"] is False, out["answer"])
    out2 = svc.answer("이 과목 꿀강?", course="존재하지않는과목XYZ")
    check("없는 과목 -> 거부", out2["answer"] == REFUSAL_MSG, out2["answer"])
    out3 = svc.answer("이 교수 어때요", professor="윤승태")
    check("있는 교수 -> 정상 답변", out3["grounded"] is True)


def demo_real_professor():
    print("\n[데모] 실제 교수 비교: 윤승태 vs 윤성민 (기독교/채플 강의)")
    svc = RagService()
    q = "이 교수님들 중 누구 수업이 학점 받기 더 좋아?"
    for prof in ("윤승태", "윤성민"):
        out = svc.answer(q, professor=prof, top_k=3)
        print(f"\n=== {prof} 교수 ===")
        print(out["answer"])
        for s in out["sources"]:
            print(f"  · {s['citation']} sim={s['score']}")


def main():
    print("=" * 60)
    print("에타 강의평 벡터DB RAG 테스트 (실제 데이터 995건)")
    print("임베딩:", "Gemini" if os.environ.get("GEMINI_API_KEY") else "LSA(오프라인)")
    print("=" * 60)
    test_store_loaded()
    test_syllabus()
    test_3_1_semantic()
    test_3_2_filter()
    test_3_3_citation()
    test_3_4_refusal()
    demo_real_professor()
    print("\n" + "=" * 60)
    print(f"결과: {PASS} PASSED, {FAIL} FAILED")
    print("=" * 60)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
