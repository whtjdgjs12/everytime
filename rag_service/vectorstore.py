# -*- coding: utf-8 -*-
"""
경량 벡터 저장소 (순수 Python/numpy)
=====================================
ChromaDB 가 이 환경에서 네이티브 코어 세그폴트로 동작하지 않아, 동일 개념을
의존성 없이 구현한 영속 벡터 인덱스다. (임베딩 행렬 저장 + 코사인 최근접 + 메타 필터)

저장 형식 (store_dir/):
  vectors.npy   : float32 [N x dim], L2 정규화된 임베딩
  rows.csv      : 벡터와 같은 순서의 메타데이터/원문 (id, school, professor, course, rating, review)
  meta.json     : {backend, dim}
  lsa_model.pkl : (LSA 백엔드일 때만) 학습된 임베더
"""
from __future__ import annotations

import json
import os
from typing import List, Optional, Sequence

import numpy as np
import pandas as pd


def _l2norm(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


class NumpyVectorStore:
    def __init__(self, vectors: np.ndarray, rows: pd.DataFrame, backend: str, dim: int):
        self.vectors = _l2norm(np.asarray(vectors, dtype=np.float32))
        self.rows = rows.reset_index(drop=True)
        self.backend = backend
        self.dim = dim

    # --- 영속화 ---
    def save(self, store_dir: str) -> None:
        os.makedirs(store_dir, exist_ok=True)
        np.save(os.path.join(store_dir, "vectors.npy"), self.vectors)
        self.rows.to_csv(os.path.join(store_dir, "rows.csv"), index=False, encoding="utf-8-sig")
        with open(os.path.join(store_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump({"backend": self.backend, "dim": int(self.dim)}, f, ensure_ascii=False)

    @classmethod
    def load(cls, store_dir: str) -> "NumpyVectorStore":
        with open(os.path.join(store_dir, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        vectors = np.load(os.path.join(store_dir, "vectors.npy"))
        rows = pd.read_csv(os.path.join(store_dir, "rows.csv"))
        return cls(vectors, rows, meta["backend"], meta["dim"])

    def count(self) -> int:
        return len(self.rows)

    # --- 검색: 코사인 유사도 top-k, 후보 인덱스 제한 가능 ---
    def query(
        self,
        query_vec: Sequence[float],
        top_k: int = 3,
        candidate_idx: Optional[Sequence[int]] = None,
    ) -> List[dict]:
        q = np.asarray(query_vec, dtype=np.float32).reshape(1, -1)
        q = _l2norm(q)[0]

        if candidate_idx is None:
            idx = np.arange(len(self.vectors))
        else:
            idx = np.asarray(list(candidate_idx), dtype=int)
            if idx.size == 0:
                return []

        sims = self.vectors[idx] @ q  # 정규화돼 있으므로 내적 = 코사인 유사도
        order = np.argsort(-sims)[:top_k]
        results = []
        for o in order:
            row_i = int(idx[o])
            row = self.rows.iloc[row_i]
            results.append({
                "id": int(row["id"]),
                "school": str(row["school"]),
                "professor": str(row["professor"]),
                "course": str(row["course"]),
                "rating": int(row["rating"]),
                "review": str(row["review"]),
                "score": round(float(sims[o]), 4),
            })
        return results
