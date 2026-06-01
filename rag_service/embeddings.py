# -*- coding: utf-8 -*-
"""
임베딩 백엔드 (네이티브 DLL 의존성 없음)
========================================
문장 -> 고정 차원 의미 벡터.

- LsaEmbedder   : TF-IDF + TruncatedSVD(LSA). 순수 sklearn, 오프라인, 키 불필요.
                  글자 단위 TF-IDF 를 잠재의미(SVD)로 압축해 단순 키워드보다 의미 검색에 가깝다.
                  코퍼스에 fit 이 필요하므로 학습된 모델을 저장/로드한다.
- GeminiEmbedder: Google text-embedding-004 (REST). 진짜 트랜스포머 임베딩. GEMINI_API_KEY 필요.

get_embedder(backend) 로 선택한다. backend="auto" 이면 키가 있으면 gemini, 없으면 lsa.
"""
from __future__ import annotations

import os
import pickle
from typing import List

import numpy as np


class LsaEmbedder:
    backend = "lsa"

    def __init__(self, n_components: int = 256):
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.decomposition import TruncatedSVD
        from sklearn.preprocessing import Normalizer
        from sklearn.pipeline import make_pipeline

        self.n_components = n_components
        self._tfidf = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=2)
        self._svd = TruncatedSVD(n_components=n_components, random_state=42)
        self._pipe = make_pipeline(self._tfidf, self._svd, Normalizer(copy=False))
        self._fitted = False
        self.dim = n_components

    def fit(self, texts: List[str]) -> "LsaEmbedder":
        n_feat_cap = max(2, min(self.n_components, len(set(texts)) - 1))
        if n_feat_cap < self.n_components:
            self._svd.n_components = n_feat_cap
            self.dim = n_feat_cap
        self._pipe.fit(texts)
        self._fitted = True
        # 실제 출력 차원 확정
        self.dim = self._svd.n_components
        return self

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not self._fitted:
            raise RuntimeError("LsaEmbedder 는 먼저 fit() 해야 합니다.")
        vecs = self._pipe.transform(texts).astype(np.float32)
        return vecs.tolist()

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            pickle.dump(self._pipe, f)

    @classmethod
    def load(cls, path: str) -> "LsaEmbedder":
        obj = cls.__new__(cls)
        with open(path, "rb") as f:
            obj._pipe = pickle.load(f)
        obj._fitted = True
        obj._svd = obj._pipe.steps[1][1]
        obj.n_components = obj._svd.n_components
        obj.dim = obj._svd.n_components
        return obj


class GeminiEmbedder:
    backend = "gemini"
    dim = 768

    def __init__(self, api_key: str, model: str = "text-embedding-004"):
        self.api_key = api_key
        self.model = model

    def fit(self, texts: List[str]) -> "GeminiEmbedder":
        return self  # 학습 불필요

    def embed(self, texts: List[str]) -> List[List[float]]:
        import requests

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:batchEmbedContents?key={self.api_key}"
        )
        out: List[List[float]] = []
        # API 배치 한도를 고려해 100개씩 끊어서 호출
        for i in range(0, len(texts), 100):
            chunk = texts[i:i + 100]
            payload = {
                "requests": [
                    {"model": f"models/{self.model}", "content": {"parts": [{"text": t}]}}
                    for t in chunk
                ]
            }
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            for emb in resp.json()["embeddings"]:
                out.append(emb["values"])
        return out

    def save(self, path: str) -> None:
        pass  # 상태 없음

    @classmethod
    def load(cls, path: str):
        raise RuntimeError("GeminiEmbedder 는 저장/로드가 필요 없습니다. 새로 생성하세요.")


def get_embedder(backend: str = "auto", api_key: str | None = None):
    """backend: 'auto' | 'lsa' | 'gemini'"""
    api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY")
    if backend == "auto":
        backend = "gemini" if api_key else "lsa"
    if backend == "gemini":
        if not api_key:
            raise ValueError("gemini 백엔드에는 GEMINI_API_KEY 가 필요합니다.")
        return GeminiEmbedder(api_key)
    return LsaEmbedder()
