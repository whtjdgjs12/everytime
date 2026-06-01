# -*- coding: utf-8 -*-
"""
에브리타임 강의평 RAG (벡터 검색 버전 · 실제 데이터)
============================================================
ingest.py 로 적재한 벡터 저장소(store/)를 사용해 의미 검색 기반 RAG 를 수행한다.

  질문 ──임베딩──> 벡터 ──벡터DB 의미검색(+메타필터)──> 근거 리뷰 top-k
       ──> 프롬프트(출처표기/환각방지) ──> Gemini 생성 또는 오프라인 요약

요구사항 매핑(project_proposal.md):
  3.1 의미 검색      -> VectorRetriever.retrieve (벡터 최근접)
  3.2 속성 필터      -> professor/course/school (메타데이터 후보 제한)
  3.3 출처 표기      -> Review.citation  (학교/과목/평점 — 실제 데이터에 학기 없음)
  3.4 환각 방지/거부 -> 관련 데이터 없으면 거부
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from embeddings import LsaEmbedder, get_embedder
from vectorstore import NumpyVectorStore

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_DIR = os.path.join(HERE, "store")
LSA_PATH = os.path.join(STORE_DIR, "lsa_model.pkl")
META_PATH = os.path.join(STORE_DIR, "meta.json")
REFUSAL_MSG = "데이터가 준비되지 않아 답변드리기 어렵습니다."


@dataclass
class Review:
    id: str
    school: str
    professor: str
    course: str
    rating: int
    review: str
    semester: str = ""       # 수강학기(크롤링 데이터에 존재)
    source: str = "review"  # "review" | "syllabus"
    score: float = 0.0       # 의미 유사도 (코사인)

    def citation(self) -> str:
        """3.3 출처 표기. 리뷰는 (학교 과목 [학기] 평점N점 리뷰 참고), 계획서는 계획서로 표기."""
        if self.source == "syllabus":
            return f"({self.school} {self.course} 강의계획서 참고)"
        sem = f" {self.semester}" if self.semester else ""
        return f"({self.school} {self.course}{sem} 평점 {self.rating}점 리뷰 참고)"

    def as_context(self) -> str:
        if self.source == "syllabus":
            return (
                f"[강의계획서 #{self.id}] 학교: {self.school} | 교수: {self.professor} | "
                f"과목: {self.course}\n내용: {self.review}"
            )
        return (
            f"[리뷰 #{self.id}] 학교: {self.school} | 교수: {self.professor} | "
            f"과목: {self.course} | 평점: {self.rating}/5\n내용: {self.review}"
        )


class VectorRetriever:
    def __init__(self, store_dir: str = STORE_DIR):
        if not os.path.exists(META_PATH):
            raise FileNotFoundError(
                "벡터 저장소가 없습니다. 먼저 'python ingest.py' 를 실행하세요."
            )
        self.store = NumpyVectorStore.load(store_dir)
        self.meta = {"backend": self.store.backend, "dim": self.store.dim}
        self.df = self.store.rows  # 부분 일치 필터 해석용 (벡터와 동일 순서)

        if self.store.backend == "lsa":
            self.embedder = LsaEmbedder.load(LSA_PATH)
        else:
            self.embedder = get_embedder("gemini")

    # --- 3.2 부분 일치 교수/과목/학교명 + 소스로 후보 행 인덱스 제한 ---
    def _candidate_idx(self, professor, course, school, source=None):
        mask = pd.Series(True, index=self.df.index)
        for field, val in (("professor", professor), ("course", course), ("school", school)):
            if val:
                mask &= self.df[field].astype(str).str.contains(re.escape(val), na=False)
        if source and "source" in self.df.columns:
            mask &= self.df["source"].astype(str) == source
        return self.df.index[mask].tolist()

    def has_data(self, professor=None, course=None, school=None, source=None) -> bool:
        if not (professor or course or school or source):
            return True
        return len(self._candidate_idx(professor, course, school, source)) > 0

    # --- 3.1 의미 검색 ---
    def retrieve(self, query, professor=None, course=None, school=None, source=None, top_k=3) -> List[Review]:
        if professor or course or school or source:
            cand = self._candidate_idx(professor, course, school, source)
            if not cand:
                return []
        else:
            cand = None
        q_vec = self.embedder.embed([query])[0]
        hits = self.store.query(q_vec, top_k=top_k, candidate_idx=cand)
        return [
            Review(
                id=h["id"], school=h["school"], professor=h["professor"],
                course=h["course"], rating=h["rating"], review=h["review"],
                semester=h.get("semester", ""), source=h.get("source", "review"),
                score=h["score"],
            )
            for h in hits
        ]


SYSTEM_INSTRUCTION = (
    "너는 에브리타임 강의평 데이터만 근거로 답하는 수강신청 AI 비서다.\n"
    "규칙:\n"
    "1. 아래 [강의평 컨텍스트] 안의 정보만 사용한다. 없는 교수/과목/사실은 절대 지어내지 않는다.\n"
    "2. 요약한 핵심 정보 끝에는 반드시 (학교 과목 평점N점 리뷰 참고) 형식의 출처를 표기한다.\n"
    "3. 학점/과제/시험 관점에서 사용자의 목표에 맞춰 비교하고 결론을 분명히 제시한다.\n"
    "4. 컨텍스트가 비어 있으면 정확히 다음 문장만 답한다: " + REFUSAL_MSG + "\n"
)


def build_prompt(query: str, contexts: List[Review]) -> str:
    ctx = "\n\n".join(c.as_context() for c in contexts) if contexts else "(없음)"
    return f"{SYSTEM_INSTRUCTION}\n[강의평 컨텍스트]\n{ctx}\n\n[사용자 질문]\n{query}\n\n[답변]"


def _gemini_generate(prompt: str, api_key: str, model: str = "gemini-1.5-flash") -> str:
    import requests

    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={api_key}")
    resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5-20251001"  # 저렴·빠름. 더 좋은 품질은 sonnet/opus


def _claude_generate(query: str, contexts: List[Review], api_key: str,
                     model: str = DEFAULT_CLAUDE_MODEL) -> str:
    """Anthropic Messages API 로 답변 생성. 시스템 프롬프트에 prompt caching 적용."""
    import requests

    ctx = "\n\n".join(c.as_context() for c in contexts) if contexts else "(없음)"
    user = f"[강의평 컨텍스트]\n{ctx}\n\n[사용자 질문]\n{query}"
    body = {
        "model": model,
        "max_tokens": 1024,
        # 매 질문마다 동일한 시스템 프롬프트 → 캐싱으로 입력 토큰 비용 절감
        "system": [{"type": "text", "text": SYSTEM_INSTRUCTION,
                    "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    resp = requests.post("https://api.anthropic.com/v1/messages",
                         headers=headers, json=body, timeout=40)
    resp.raise_for_status()
    data = resp.json()
    return "".join(b.get("text", "") for b in data.get("content", [])
                   if b.get("type") == "text").strip()


def _offline_generate(query: str, contexts: List[Review]) -> str:
    if not contexts:
        return REFUSAL_MSG

    reviews = [c for c in contexts if c.source != "syllabus"]
    syllabi = [c for c in contexts if c.source == "syllabus"]
    lines = []

    if reviews:
        by_prof: dict[str, List[Review]] = {}
        for c in reviews:
            by_prof.setdefault(c.professor, []).append(c)
        lines.append("[강의평 근거 기반 요약]")
        summaries = []
        for prof, revs in by_prof.items():
            avg = sum(r.rating for r in revs) / len(revs)
            courses = ", ".join(sorted({r.course for r in revs}))
            cites = " ".join(r.citation() for r in revs)
            lines.append(f"- {prof} 교수 (과목: {courses}): 평균 평점 {avg:.1f}/5 {cites}")
            summaries.append((prof, avg))
        if len(summaries) >= 2:
            best = max(summaries, key=lambda s: s[1])
            lines.append(f"[결론] 평점만 보면 '{best[0]}' 교수님 강의평이 가장 긍정적입니다 "
                         f"(평균 {best[1]:.1f}/5).")

    if syllabi:
        lines.append("\n[강의계획서 참고 정보]")
        for s in syllabi:
            snippet = s.review[:120].strip()
            lines.append(f"- {s.course} ({s.professor}): {snippet}... {s.citation()}")

    return "\n".join(lines)


class RagService:
    def __init__(self, llm: str = "auto", model: Optional[str] = None):
        self.retriever = VectorRetriever()
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        self.gemini_key = os.environ.get("GEMINI_API_KEY")
        self.model = model
        # 백엔드 선택: auto → claude > gemini > offline
        if llm == "auto":
            llm = "claude" if self.anthropic_key else ("gemini" if self.gemini_key else "offline")
        self.llm = llm

    def answer(self, query, professor=None, course=None, school=None, source=None, top_k=3) -> dict:
        # 3.4 Zero-Hallucination
        if (professor or course or school or source) and \
                not self.retriever.has_data(professor, course, school, source):
            return {"answer": REFUSAL_MSG, "grounded": False, "sources": []}

        contexts = self.retriever.retrieve(query, professor, course, school, source, top_k)
        if not contexts:
            return {"answer": REFUSAL_MSG, "grounded": False, "sources": []}

        if self.llm == "claude" and self.anthropic_key:
            try:
                text = _claude_generate(query, contexts, self.anthropic_key,
                                        self.model or DEFAULT_CLAUDE_MODEL)
                mode = f"claude ({self.model or DEFAULT_CLAUDE_MODEL})"
            except Exception as e:
                text = _offline_generate(query, contexts)
                mode = f"offline (claude 실패: {type(e).__name__})"
        elif self.llm == "gemini" and self.gemini_key:
            try:
                text = _gemini_generate(build_prompt(query, contexts), self.gemini_key)
                mode = "gemini"
            except Exception as e:
                text = _offline_generate(query, contexts)
                mode = f"offline (gemini 실패: {type(e).__name__})"
        else:
            text = _offline_generate(query, contexts)
            mode = "offline"

        return {
            "answer": text,
            "grounded": True,
            "mode": mode,
            "embedding_backend": self.retriever.meta["backend"],
            "sources": [
                {
                    "id": c.id, "source": c.source, "school": c.school,
                    "professor": c.professor, "course": c.course,
                    "semester": c.semester, "rating": c.rating,
                    "citation": c.citation(), "score": c.score,
                }
                for c in contexts
            ],
        }


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="에타 강의평 RAG (ChromaDB · 실제 데이터)")
    p.add_argument("query", nargs="?")
    p.add_argument("--professor", "-p", default=None)
    p.add_argument("--course", "-c", default=None)
    p.add_argument("--school", "-s", default=None)
    p.add_argument("--source", default=None, choices=["review", "syllabus"],
                   help="review 또는 syllabus 만 검색")
    p.add_argument("--llm", default="auto", choices=["auto", "claude", "gemini", "offline"],
                   help="답변 생성 백엔드 (기본 auto: 키 있으면 claude>gemini, 없으면 offline)")
    p.add_argument("--model", default=None, help="Claude 모델 ID (예: claude-sonnet-4-6)")
    p.add_argument("--top_k", "-k", type=int, default=3)
    args = p.parse_args()

    svc = RagService(llm=args.llm, model=args.model)
    if not args.query:
        print("에타 강의평 RAG (종료: 나가기)\n")
        while True:
            q = input("질문> ").strip()
            if q in ("나가기", "exit", "quit", ""):
                break
            print("\n" + svc.answer(q, args.professor, args.course, args.school,
                                    args.source, args.top_k)["answer"] + "\n")
    else:
        res = svc.answer(args.query, args.professor, args.course, args.school,
                         args.source, args.top_k)
        print(json.dumps(res, ensure_ascii=False, indent=2))
