# -*- coding: utf-8 -*-
"""
실제 에브리타임 강의평 CSV 6개(학교별)를 하나로 통합·정제한다.
원본: ../evrytime-emotion-prediction-master/data/*.csv  (컬럼: Prof, Lec, Star, Reviews)
출력: reviews_real.csv  (컬럼: id, school, professor, course, rating, review)

실행: python build_dataset.py
"""
from __future__ import annotations

import glob
import os
import re

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "evrytime-emotion-prediction-master", "data")
OUT_PATH = os.path.join(HERE, "reviews_real.csv")


def school_name(filename: str) -> str:
    """'강대에타.csv' -> '강대'"""
    base = os.path.splitext(os.path.basename(filename))[0]
    return base.replace("에타", "").strip()


def clean_text(s: str) -> str:
    s = str(s).replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def build() -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*.csv")))
    if not files:
        raise FileNotFoundError(f"원본 CSV를 찾을 수 없습니다: {DATA_DIR}")

    frames = []
    for f in files:
        df = pd.read_csv(f)
        df = df.rename(
            columns={"Prof": "professor", "Lec": "course", "Star": "rating", "Reviews": "review"}
        )
        df = df[["professor", "course", "rating", "review"]].copy()
        df["school"] = school_name(f)
        frames.append(df)

    merged = pd.concat(frames, ignore_index=True)

    # 정제
    for col in ["professor", "course", "review"]:
        merged[col] = merged[col].map(clean_text)
    merged["rating"] = pd.to_numeric(merged["rating"], errors="coerce")

    before = len(merged)
    merged = merged[merged["review"].str.len() >= 5]          # 너무 짧은 리뷰 제거
    merged = merged[merged["rating"].between(1, 5)]            # 평점 1~5만
    merged = merged.dropna(subset=["professor", "course", "review", "rating"])
    merged = merged.drop_duplicates(subset=["professor", "course", "review"])  # 완전 중복 제거
    merged["rating"] = merged["rating"].astype(int)

    merged = merged.reset_index(drop=True)
    merged.insert(0, "id", merged.index + 1)
    merged = merged[["id", "school", "professor", "course", "rating", "review"]]

    print(f"원본 {before}건 -> 정제 후 {len(merged)}건 "
          f"(제거 {before - len(merged)}건)")
    print("학교별 건수:")
    print(merged["school"].value_counts().to_string())
    print(f"교수 수: {merged['professor'].nunique()}, 과목 수: {merged['course'].nunique()}")
    return merged


if __name__ == "__main__":
    df = build()
    df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"\n저장 완료: {OUT_PATH}")
