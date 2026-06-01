# -*- coding: utf-8 -*-
"""
크롤링 보조 파싱 함수 (브라우저·네트워크 의존 없음 → 단위 테스트 가능)
"""
from __future__ import annotations

import re


def width_to_stars(style_or_pct) -> int:
    """에타 별점은 보통 채워진 별의 width % 로 렌더된다. 'width: 80%' → 4점.
    숫자(%)나 'width:NN%' 문자열 모두 허용. 0~5 로 클램프."""
    if style_or_pct is None:
        return 0
    s = str(style_or_pct)
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", s)
    if m:
        pct = float(m.group(1))
    else:
        try:
            pct = float(s)
        except ValueError:
            return 0
    stars = round(pct / 20.0)            # 100% = 5점
    return max(0, min(5, int(stars)))


def text_to_stars(text) -> int:
    """'4.0' / '평점 3' 같은 텍스트에서 평점 숫자 추출. 실패 시 0."""
    if not text:
        return 0
    m = re.search(r"([0-5](?:\.\d)?)", str(text))
    if not m:
        return 0
    return max(0, min(5, round(float(m.group(1)))))


def clean_review_text(text) -> str:
    """리뷰 본문 정제: 공백 정규화, 양끝 트림."""
    if not text:
        return ""
    t = str(text).replace("\r", " ").replace("\n", " ")
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def canonical_course(name, targets) -> str:
    """공백 차이 등으로 갈라진 동일 과목명을 대표 과목명(targets 중 하나)으로 통일.
    예: '확률과통계' → '확률과 통계'. 매칭 없으면 양끝 공백만 제거."""
    key = re.sub(r"\s+", "", str(name))
    for t in targets:
        if re.sub(r"\s+", "", str(t)) == key:
            return str(t)
    return str(name).strip()


def course_matches(target: str, lecture_name: str) -> bool:
    """검색 결과의 강의명이 대상 과목명과 일치하는지(공백 무시 부분일치)."""
    def norm(x):
        return re.sub(r"\s+", "", str(x))
    return norm(target) in norm(lecture_name) or norm(lecture_name) in norm(target)
