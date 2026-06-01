# -*- coding: utf-8 -*-
"""
실제 강의평(reviews_real.csv)을 임베딩하여 벡터 저장소(store/)에 적재한다.
(velog RAG 구조의 '인덱싱' 단계 — 벡터DB 빌드)

  reviews_real.csv ──임베딩(LSA 또는 Gemini)──> 벡터 ──> NumpyVectorStore(store/)
                     + 메타데이터(school, professor, course, rating, review)

실행:
  python ingest.py                       # 오프라인 LSA 임베딩 (키 불필요)
  GEMINI_API_KEY=... python ingest.py --backend gemini   # 진짜 의미 임베딩
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

from embeddings import get_embedder, LsaEmbedder
from vectorstore import NumpyVectorStore

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "reviews_real.csv")
SYLLABI_PATH = os.path.join(HERE, "syllabi.csv")
STORE_DIR = os.path.join(HERE, "store")
LSA_PATH = os.path.join(STORE_DIR, "lsa_model.pkl")

COLUMNS = ["id", "school", "professor", "course", "semester", "rating", "review", "source"]


def doc_text(row) -> str:
    """임베딩/검색 대상 문서. 리뷰는 평점 맥락 포함, 계획서는 본문 위주."""
    if row["source"] == "syllabus":
        return f"강의계획서 {row['course']} {row['professor']} {row['review']}"
    return f"{row['course']} {row['professor']} 평점{row['rating']} {row['review']}"


def _coerce(df: pd.DataFrame, default_source: str) -> pd.DataFrame:
    """누락 컬럼을 기본값으로 채워 통합 스키마에 맞춘다(구버전 CSV 호환)."""
    if "source" not in df.columns:
        df["source"] = default_source
    if "semester" not in df.columns:
        df["semester"] = ""
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return df[COLUMNS]


def _load_unified() -> pd.DataFrame:
    """리뷰 + (있으면) 강의계획서를 동일 스키마로 통합."""
    frames = []
    rv = _coerce(pd.read_csv(CSV_PATH), "review")
    frames.append(rv)
    print(f"리뷰 {len(rv)}건 로드")

    if os.path.exists(SYLLABI_PATH):
        sy = _coerce(pd.read_csv(SYLLABI_PATH), "syllabus")
        frames.append(sy)
        print(f"강의계획서 청크 {len(sy)}건 로드")
    else:
        print("강의계획서 없음 (syllabi.csv) — 리뷰만 적재. 'python build_syllabi.py' 로 생성 가능")

    df = pd.concat(frames, ignore_index=True)
    df["id"] = df["id"].astype(str)
    df["semester"] = df["semester"].fillna("")
    return df


def store_exists() -> bool:
    return os.path.exists(os.path.join(STORE_DIR, "meta.json"))


def build_store(backend: str = "auto") -> int:
    """reviews_real.csv(+syllabi) → 임베딩 → 벡터 저장소. 적재 건수 반환. (앱에서도 호출)"""
    df = _load_unified()
    print(f"통합 문서 {len(df)}건 (리뷰+계획서)")
    docs = [doc_text(r) for _, r in df.iterrows()]

    embedder = get_embedder(backend)
    print(f"임베딩 백엔드: {embedder.backend}")
    embedder.fit(docs)
    vectors = np.asarray(embedder.embed(docs), dtype=np.float32)
    store = NumpyVectorStore(vectors, df, embedder.backend, embedder.dim)
    store.save(STORE_DIR)
    if isinstance(embedder, LsaEmbedder):
        embedder.save(LSA_PATH)
    print(f"벡터 저장소 적재 완료: {store.count()}건 -> {STORE_DIR}")
    return store.count()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="auto", choices=["auto", "lsa", "gemini"])
    args = parser.parse_args()

    df = _load_unified()
    print(f"통합 문서 {len(df)}건 (리뷰+계획서)")

    docs = [doc_text(r) for _, r in df.iterrows()]

    embedder = get_embedder(args.backend)
    print(f"임베딩 백엔드: {embedder.backend}")
    embedder.fit(docs)
    print("임베딩 계산 중...")
    vectors = np.asarray(embedder.embed(docs), dtype=np.float32)
    print(f"임베딩 완료: {vectors.shape[0]}개 x {vectors.shape[1]}차원")

    store = NumpyVectorStore(vectors, df, embedder.backend, embedder.dim)
    store.save(STORE_DIR)
    print(f"벡터 저장소 적재 완료: {store.count()}건 -> {STORE_DIR}")

    if isinstance(embedder, LsaEmbedder):
        embedder.save(LSA_PATH)
        print(f"LSA 모델 저장: {LSA_PATH}")
    print("완료.")


if __name__ == "__main__":
    main()
