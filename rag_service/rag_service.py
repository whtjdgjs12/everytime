# -*- coding: utf-8 -*-
"""
에브리타임 교수 리뷰 RAG AI 분석 서비스 (PoC)
=================================================
project_proposal.md 의 기능 요구사항 구현체.

  3.1 자연어 맥락 기반 RAG 의미 검색  -> RagRetriever.retrieve (TF-IDF 코사인 유사도 top-k)
  3.2 정밀한 학계/과목 속성 필터       -> retrieve(professor=..., course=...)
  3.3 투명한 출처 표기 (Strict Grounding) -> build_prompt + _format_context (수강학기/평점 자동 표기)
  3.4 솔직한 답변 거부권 (Zero-Hallucination) -> answer() 에서 관련 데이터 없을 시 거부

생성(LLM) 단계는 GEMINI_API_KEY 환경변수가 있으면 Gemini REST API 를 호출하고,
없으면 검색 결과를 그대로 근거 표기하여 요약하는 오프라인 폴백으로 동작한다.
(오프라인 폴백 덕분에 API 키 없이도 전체 파이프라인 테스트가 가능하다.)
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

REFUSAL_MSG = "데이터가 준비되지 않아 답변드리기 어렵습니다."


@dataclass
class Review:
    id: int
    professor: str
    course: str
    semester: str
    rating: int
    assignment_load: str
    exam_type: str
    review: str
    score: float = 0.0  # 검색 유사도 점수

    def citation(self) -> str:
        """3.3 출처 표기: (2025년 2학기 평점 5점 리뷰 참고)"""
        return f"({self.semester} 평점 {self.rating}점 리뷰 참고)"

    def as_context(self) -> str:
        return (
            f"[리뷰 #{self.id}] 교수: {self.professor} | 과목: {self.course} | "
            f"학기: {self.semester} | 평점: {self.rating}/5 | "
            f"과제부담: {self.assignment_load} | 시험유형: {self.exam_type}\n"
            f"내용: {self.review}"
        )


class RagRetriever:
    """리뷰 CSV 를 적재하고 의미 검색(TF-IDF 코사인) + 속성 필터를 제공."""

    def __init__(self, csv_path: str):
        self.df = pd.read_csv(csv_path)
        self._validate_schema()
        # 한국어는 형태소 분석기 없이도 문자 n-gram TF-IDF 가 강건하게 동작한다.
        # (운영 단계에서는 Gemini text-embedding 으로 교체 가능 — 인터페이스 동일)
        self._vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        corpus = (
            self.df["course"].astype(str) + " "
            + self.df["professor"].astype(str) + " "
            + self.df["review"].astype(str)
        )
        self._matrix = self._vectorizer.fit_transform(corpus)

    EXPECTED_COLS = [
        "id", "professor", "course", "semester",
        "rating", "assignment_load", "exam_type", "review",
    ]

    def _validate_schema(self) -> None:
        missing = [c for c in self.EXPECTED_COLS if c not in self.df.columns]
        if missing:
            raise ValueError(f"reviews.csv 스키마 누락 컬럼: {missing}")

    # --- 3.2 속성 필터 ---
    def _filter_mask(self, professor: Optional[str], course: Optional[str]):
        mask = pd.Series(True, index=self.df.index)
        if professor:
            mask &= self.df["professor"].str.contains(re.escape(professor), na=False)
        if course:
            mask &= self.df["course"].str.contains(re.escape(course), na=False)
        return mask

    def has_data(self, professor: Optional[str] = None, course: Optional[str] = None) -> bool:
        return bool(self._filter_mask(professor, course).any())

    # --- 3.1 의미 검색 top-k ---
    def retrieve(
        self,
        query: str,
        professor: Optional[str] = None,
        course: Optional[str] = None,
        top_k: int = 3,
    ) -> List[Review]:
        mask = self._filter_mask(professor, course)
        candidate_idx = self.df.index[mask].tolist()
        if not candidate_idx:
            return []

        q_vec = self._vectorizer.transform([query])
        sims = cosine_similarity(q_vec, self._matrix[candidate_idx]).ravel()

        ranked = sorted(zip(candidate_idx, sims), key=lambda x: x[1], reverse=True)
        results: List[Review] = []
        for idx, score in ranked[:top_k]:
            row = self.df.loc[idx]
            results.append(
                Review(
                    id=int(row["id"]),
                    professor=str(row["professor"]),
                    course=str(row["course"]),
                    semester=str(row["semester"]),
                    rating=int(row["rating"]),
                    assignment_load=str(row["assignment_load"]),
                    exam_type=str(row["exam_type"]),
                    review=str(row["review"]),
                    score=float(score),
                )
            )
        return results


# --- 3.3 + 3.4 프롬프트 구성 (Strict Grounding / Zero-Hallucination) ---
SYSTEM_INSTRUCTION = (
    "너는 에브리타임 강의평 데이터만 근거로 답하는 수강신청 AI 비서다.\n"
    "규칙:\n"
    "1. 아래 제공된 [강의평 컨텍스트] 안의 정보만 사용한다. 컨텍스트에 없는 교수/과목/사실은 절대 지어내지 않는다.\n"
    "2. 요약한 모든 핵심 정보 끝에는 반드시 근거가 된 리뷰의 (수강학기 평점N점 리뷰 참고) 를 괄호로 표기한다.\n"
    "3. 학점/과제/시험 관점에서 사용자의 목표에 맞춰 비교하고 결론(추천)을 분명히 제시한다.\n"
    "4. 컨텍스트가 비어 있으면 정확히 다음 문장만 답한다: " + REFUSAL_MSG + "\n"
)


def build_prompt(query: str, contexts: List[Review]) -> str:
    ctx_block = "\n\n".join(c.as_context() for c in contexts) if contexts else "(없음)"
    return (
        f"{SYSTEM_INSTRUCTION}\n"
        f"[강의평 컨텍스트]\n{ctx_block}\n\n"
        f"[사용자 질문]\n{query}\n\n"
        f"[답변]"
    )


def _gemini_generate(prompt: str, api_key: str, model: str = "gemini-1.5-flash") -> str:
    """Gemini REST 호출 (requests 사용). 실패 시 예외 발생."""
    import requests

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def _offline_generate(query: str, contexts: List[Review]) -> str:
    """API 키가 없을 때의 결정론적 요약기.
    근거 표기(3.3)와 비교 결론을 규칙 기반으로 생성하여 파이프라인을 검증 가능하게 한다."""
    if not contexts:
        return REFUSAL_MSG

    # 교수별 그룹화하여 평균 평점 / 과제부담 / 시험유형 요약
    by_prof: dict[str, List[Review]] = {}
    for c in contexts:
        by_prof.setdefault(c.professor, []).append(c)

    lines = ["[강의평 근거 기반 요약]"]
    summaries = []
    for prof, revs in by_prof.items():
        avg = sum(r.rating for r in revs) / len(revs)
        loads = ", ".join(sorted({r.assignment_load for r in revs}))
        exams = ", ".join(sorted({r.exam_type for r in revs}))
        cites = " ".join(r.citation() for r in revs)
        lines.append(
            f"- {prof} 교수: 평균 평점 {avg:.1f}/5, 과제부담 [{loads}], "
            f"시험유형 [{exams}] {cites}"
        )
        summaries.append((prof, avg, loads))

    # 비교 결론: 평균 평점이 높고 과제부담이 낮은 쪽을 학점 방어용으로 추천
    def burden_rank(load_str: str) -> int:
        order = {"적음": 0, "보통": 1, "많음": 2}
        return min((order.get(x.strip(), 1) for x in load_str.split(",")), default=1)

    if len(summaries) >= 2:
        best = sorted(summaries, key=lambda s: (-s[1], burden_rank(s[2])))[0]
        lines.append(
            f"\n[결론] 학점 방어가 목표라면 평균 평점이 높고 과제 부담이 낮은 "
            f"'{best[0]}' 교수님 수업이 더 유리합니다."
        )
    else:
        only = summaries[0]
        lines.append(
            f"\n[결론] '{only[0]}' 교수님 수업의 강의평 근거는 위와 같습니다."
        )
    return "\n".join(lines)


class RagService:
    """검색 + 생성을 묶은 최종 서비스 진입점."""

    def __init__(self, csv_path: str, api_key: Optional[str] = None):
        self.retriever = RagRetriever(csv_path)
        self.api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY")

    def answer(
        self,
        query: str,
        professor: Optional[str] = None,
        course: Optional[str] = None,
        top_k: int = 3,
    ) -> dict:
        # 3.4 Zero-Hallucination: 필터에 해당하는 데이터가 아예 없으면 즉시 거부
        if (professor or course) and not self.retriever.has_data(professor, course):
            return {
                "answer": REFUSAL_MSG,
                "grounded": False,
                "sources": [],
            }

        contexts = self.retriever.retrieve(query, professor, course, top_k)
        if not contexts:
            return {"answer": REFUSAL_MSG, "grounded": False, "sources": []}

        if self.api_key:
            try:
                text = _gemini_generate(build_prompt(query, contexts), self.api_key)
                mode = "gemini"
            except Exception as e:  # 네트워크/키 오류 시 폴백
                text = _offline_generate(query, contexts)
                mode = f"offline (gemini 실패: {type(e).__name__})"
        else:
            text = _offline_generate(query, contexts)
            mode = "offline"

        return {
            "answer": text,
            "grounded": True,
            "mode": mode,
            "sources": [
                {
                    "id": c.id,
                    "professor": c.professor,
                    "course": c.course,
                    "semester": c.semester,
                    "rating": c.rating,
                    "citation": c.citation(),
                    "score": round(c.score, 4),
                }
                for c in contexts
            ],
        }


def _default_csv() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "reviews.csv")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="에타 교수 리뷰 RAG AI 비서")
    parser.add_argument("query", nargs="?", help="자연어 질문")
    parser.add_argument("--professor", "-p", default=None)
    parser.add_argument("--course", "-c", default=None)
    parser.add_argument("--top_k", "-k", type=int, default=3)
    parser.add_argument("--csv", default=_default_csv())
    args = parser.parse_args()

    svc = RagService(args.csv)

    if not args.query:
        # 대화형 데모
        print("에타 교수 리뷰 RAG AI 비서 (종료: 나가기)\n")
        while True:
            q = input("질문> ").strip()
            if q in ("나가기", "exit", "quit", ""):
                break
            res = svc.answer(q, args.professor, args.course, args.top_k)
            print("\n" + res["answer"] + "\n")
    else:
        res = svc.answer(args.query, args.professor, args.course, args.top_k)
        print(json.dumps(res, ensure_ascii=False, indent=2))
