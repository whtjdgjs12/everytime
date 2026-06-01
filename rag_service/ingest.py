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
STORE_DIR = os.path.join(HERE, "store")
LSA_PATH = os.path.join(STORE_DIR, "lsa_model.pkl")


def doc_text(row) -> str:
    """임베딩/검색 대상 문서: 과목·교수 맥락 + 리뷰 본문."""
    return f"{row['course']} {row['professor']} 평점{row['rating']} {row['review']}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="auto", choices=["auto", "lsa", "gemini"])
    parser.add_argument("--csv", default=CSV_PATH)
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    print(f"리뷰 {len(df)}건 로드")

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
