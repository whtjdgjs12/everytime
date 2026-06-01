# -*- coding: utf-8 -*-
"""
강의계획서 PDF(../temp_pdf/*.pdf)를 텍스트 추출·중복제거·청킹하여 syllabi.csv 로 만든다.
(pdfminer.six 사용 — ToUnicode 폰트맵을 읽어 한글 정상 추출)

출력 syllabi.csv 는 reviews_real.csv 와 동일한 통합 스키마를 따른다:
  id, school, professor, course, rating, review, source
  - rating = -1 (강의계획서는 평점 없음)
  - review = 계획서 텍스트 청크
  - source = "syllabus"

실행: python build_syllabi.py
"""
from __future__ import annotations

import glob
import hashlib
import os
import re

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PDF_DIR = os.path.join(HERE, "..", "temp_pdf")
OUT_PATH = os.path.join(HERE, "syllabi.csv")

CHUNK_SIZE = 450
CHUNK_OVERLAP = 80


def _clean(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


def _field(txt: str, label: str) -> str:
    m = re.search(re.escape(label) + r"\s*\n+\s*([^\n]+)", txt)
    return m.group(1).strip() if m else ""


def _semester(txt: str) -> str:
    m = re.search(r"\[([0-9]{4}-[0-9]학기)\]", txt)
    return m.group(1) if m else ""


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    text = _clean(text).replace("\n", " ")
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i:i + size].strip())
        i += size - overlap
    return [c for c in chunks if len(c) >= 30]


def build() -> pd.DataFrame:
    from pdfminer.high_level import extract_text

    files = sorted(glob.glob(os.path.join(PDF_DIR, "*.pdf")))
    if not files:
        raise FileNotFoundError(f"PDF를 찾을 수 없습니다: {PDF_DIR}")
    print(f"PDF {len(files)}개 발견")

    # 텍스트 추출 + 중복 제거(동일 내용 계획서는 1개만)
    seen, unique = {}, []
    for f in files:
        t = extract_text(f) or ""
        h = hashlib.md5(t.encode()).hexdigest()
        if h in seen:
            seen[h].append(os.path.basename(f))
            continue
        seen[h] = [os.path.basename(f)]
        unique.append((f, t))
    print(f"중복 제거 후 고유 계획서: {len(unique)}종 (원본 {len(files)}개)")

    rows = []
    sid = 0
    for f, t in unique:
        course = _field(t, "교과목명") or os.path.basename(f)
        prof = _field(t, "교수성명") or "미상"
        soc = _field(t, "교수소속")
        school = "가천대" if "가천" in t else (soc.split()[0] if soc else "미상")
        sem = _semester(t)
        for ci, ch in enumerate(chunk_text(t)):
            sid += 1
            rows.append({
                "id": f"S{sid}",
                "school": school,
                "professor": prof,
                # 과목명에 학기 맥락을 붙여 검색·표기를 풍부하게
                "course": course,
                "rating": -1,
                "review": ch,
                "source": "syllabus",
            })
    df = pd.DataFrame(rows)
    print(f"청크 생성: {len(df)}개")
    if not df.empty:
        print("과목:", df['course'].unique().tolist(),
              "| 교수:", df['professor'].unique().tolist(),
              "| 학교:", df['school'].unique().tolist())
    return df


if __name__ == "__main__":
    df = build()
    df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"\n저장 완료: {OUT_PATH}")
