# -*- coding: utf-8 -*-
"""
RAG 서비스 검증 테스트 (API 키 없이 오프라인으로 전 기능 검증)
project_proposal.md 3.1~3.4 요구사항 + 페르소나 시나리오를 자동 검증한다.
실행: python test_rag.py
"""
import os
import sys

from rag_service import RagService, RagRetriever, REFUSAL_MSG, _default_csv

CSV = _default_csv()
PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


def test_schema_and_count():
    print("\n[데이터셋] 8개 스키마 / 29개 레코드 (proposal 4.1)")
    r = RagRetriever(CSV)
    check("8개 스키마 컬럼", list(r.df.columns) == RagRetriever.EXPECTED_COLS,
          str(list(r.df.columns)))
    check("29개 모의 데이터", len(r.df) == 29, f"실제 {len(r.df)}건")
    check("CS 교수 5명", r.df["professor"].nunique() == 5,
          str(sorted(r.df["professor"].unique())))


def test_3_1_semantic_search():
    print("\n[3.1] 자연어 의미 검색 top-3")
    r = RagRetriever(CSV)
    res = r.retrieve("과제 적고 학점 잘 주는 꿀강 찾아줘", top_k=3)
    check("top-3 결과 반환", len(res) == 3, f"{len(res)}건")
    check("유사도 내림차순 정렬", all(res[i].score >= res[i+1].score for i in range(len(res)-1)))
    # 꿀강 질의이므로 상위 결과 평점이 높아야 자연스러움
    check("의미적으로 높은 평점 우선", res[0].rating >= 4, f"top1 평점 {res[0].rating}")


def test_3_2_filter():
    print("\n[3.2] 교수/과목 속성 필터")
    r = RagRetriever(CSV)
    res = r.retrieve("수업 어때", professor="박민수", course="컴퓨터네트워크", top_k=5)
    check("필터 결과 존재", len(res) > 0)
    check("교수 필터 정확", all(x.professor == "박민수" for x in res))
    check("과목 필터 정확", all(x.course == "컴퓨터네트워크" for x in res))


def test_3_3_grounding_citation():
    print("\n[3.3] 출처 표기 (Strict Grounding)")
    r = RagRetriever(CSV)
    rev = r.retrieve("꿀강", top_k=1)[0]
    cite = rev.citation()
    check("학기 포함", rev.semester in cite, cite)
    check("평점 포함", f"평점 {rev.rating}점" in cite, cite)
    check("리뷰 참고 형식", cite.endswith("리뷰 참고)"), cite)

    svc = RagService(CSV)
    out = svc.answer("컴퓨터네트워크 꿀강 추천", course="컴퓨터네트워크")
    check("답변에 출처 괄호 표기 존재", "리뷰 참고)" in out["answer"], out["answer"][:80])
    check("sources 메타데이터 반환", len(out["sources"]) > 0)


def test_3_4_zero_hallucination():
    print("\n[3.4] 환각 방지 / 답변 거부")
    svc = RagService(CSV)
    # 존재하지 않는 교수
    out = svc.answer("이 교수님 수업 어때요?", professor="존재하지않는교수")
    check("없는 교수 -> 거부", out["answer"] == REFUSAL_MSG and out["grounded"] is False,
          out["answer"])
    # 존재하지 않는 과목
    out2 = svc.answer("이 과목 꿀강?", course="양자컴퓨팅실습")
    check("없는 과목 -> 거부", out2["answer"] == REFUSAL_MSG, out2["answer"])
    # 데이터에 있는 과목은 거부하지 않아야 함
    out3 = svc.answer("운영체제 꿀강?", course="운영체제")
    check("있는 과목 -> 정상 답변", out3["grounded"] is True)


def test_persona_scenario():
    print("\n[페르소나] 김컴공: 학점 3.5 목표, 컴퓨터네트워크 홍길동 vs 박민수")
    svc = RagService(CSV)
    q = ("이번 학기 학점 3.5 이상 받는 게 목표인데, 컴퓨터네트워크 과목 "
         "홍길동 교수님이랑 박민수 교수님 중 누구 수업이 유리할까?")
    # 두 교수 모두 컨텍스트에 넣기 위해 과목만 필터, 충분한 top_k
    out = svc.answer(q, course="컴퓨터네트워크", top_k=6)
    print("\n--- AI 답변 ---")
    print(out["answer"])
    print("--- 출처 ---")
    for s in out["sources"]:
        print(f"  #{s['id']} {s['professor']} {s['course']} {s['citation']} (sim={s['score']})")
    check("정상 grounded 답변", out["grounded"] is True)
    # 데이터상 홍길동(고평점/과제적음)이 학점 방어에 유리 -> 결론에 홍길동 추천
    check("결론에 홍길동 추천", "홍길동" in out["answer"] and "결론" in out["answer"],
          out["answer"][-120:])


def main():
    print("=" * 60)
    print("에타 교수 리뷰 RAG 서비스 테스트")
    print("API 키:", "설정됨(Gemini)" if os.environ.get("GEMINI_API_KEY") else "없음(오프라인 폴백)")
    print("=" * 60)
    test_schema_and_count()
    test_3_1_semantic_search()
    test_3_2_filter()
    test_3_3_grounding_citation()
    test_3_4_zero_hallucination()
    test_persona_scenario()
    print("\n" + "=" * 60)
    print(f"결과: {PASS} PASSED, {FAIL} FAILED")
    print("=" * 60)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
