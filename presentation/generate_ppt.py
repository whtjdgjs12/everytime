# -*- coding: utf-8 -*-
"""
발표자료(PPTX) 생성기 — 에타 강의평 RAG 프로젝트.
실행: python generate_ppt.py  →  강의평RAG_발표자료.pptx
"""
import os

from pptx import Presentation
from pptx.util import Pt, Inches
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "강의평RAG_발표자료.pptx")

FONT = "맑은 고딕"
NAVY = RGBColor(0x1F, 0x2A, 0x44)
RED = RGBColor(0xE0, 0x32, 0x2E)
GRAY = RGBColor(0x55, 0x55, 0x55)

SLIDES = [
    ("__title__",
     "에브리타임 강의평 기반\nRAG 수강신청 AI 비서",
     "우리 학교 실제 강의평을 근거로, 자연어 한 줄에 맞춤 수강 추천\n가천대 5과목 · 직접 크롤링 187건 · Claude RAG"),

    ("문제 (Pain Points)", [
        "수강신청 때마다 강의평 수십~수백 개를 직접 스크롤·비교 → 시간 낭비",
        "'학점 3.5 사수', '과제 적은 과목' 같은 개인 목표 맞춤 추천이 없음",
        "일반 AI 챗봇은 우리 학교 강의평을 몰라 거짓 정보(환각)를 답함",
        "→ 우리 학교 데이터에 근거해 답하는 지능형 비서가 필요",
    ]),

    ("해결: RAG (검색 증강 생성)", [
        "RAG = '오픈북 시험' 방식 AI",
        "① 검색(Retrieval): 강의평 DB에서 질문 관련 리뷰를 찾아옴",
        "② 생성(Generation): 찾아온 리뷰'만' 근거로 답을 생성",
        "모델 재학습이 아님 → 데이터만 바꾸면 즉시 우리 학교용으로 동작",
        "환각 방지: 근거 없으면 '데이터 없음'이라 솔직히 거부",
    ]),

    ("데이터: 직접 수집한 실제 강의평", [
        "대상: 가천대 5과목",
        "  · 확률과 통계 · 모바일프로그래밍 · 빅데이터분석개론",
        "  · 스마트기기시스템 · 블록체인개론",
        "수집: Playwright 브라우저 자동화로 강의평 187건 크롤링",
        "스키마: 학교·교수·과목·수강학기·평점·리뷰",
        "정제: 중복 제거, 외국인반/공학인증/영어강의 제외, 과목명 통일",
    ]),

    ("시스템 아키텍처", [
        "[크롤러] everytime_crawler.py (Playwright)",
        "   → reviews_real.csv (187건)",
        "[인덱싱] 임베딩(LSA) → 벡터 저장소(numpy)  ingest.py",
        "[검색] 질문 임베딩 → 코사인 최근접 top-k + 교수/과목 필터",
        "[생성] Claude API (없으면 규칙기반 오프라인 폴백)",
        "[서비스] Streamlit 채팅 웹앱 (공개 URL)",
    ]),

    ("핵심 기능 (요구사항 3.1~3.4)", [
        "3.1 의미 검색: 글자가 안 겹쳐도 뜻으로 관련 강의평 top-k 검색",
        "3.2 속성 필터: 교수·과목으로 좁혀서 정확도 향상",
        "3.3 출처 표기: (가천대 모바일프로그래밍 26년 1학기 평점 5점 리뷰 참고)",
        "3.4 환각 방지: 데이터 없는 교수/과목은 솔직히 답변 거부",
    ]),

    ("기술 의사결정 · 트러블슈팅", [
        "ChromaDB·onnx·torch가 환경에서 네이티브 충돌(세그폴트)",
        "  → 순수 numpy 벡터 저장소로 동일 기능 구현(의존성 0)",
        "에타는 Vue SPA: 요소 렌더 대기 + 강의평 탭 URL 직접 이동",
        "검색→클릭 방식의 멈춤 → 강의 URL 수집 후 직접 이동으로 해결",
        "약관·계정 보호: 자동수집 리스크 인지, 최소 요청·지연 적용",
    ]),

    ("답변 생성: Claude API", [
        "생성 백엔드: Claude (기본 Haiku 4.5) / 키 없으면 오프라인 요약",
        "프롬프트 캐싱으로 반복 입력 토큰 비용 절감",
        "비용(대략): 질문 1건 ≈ 6원(Haiku) — 하루 수십 질문도 월 수천 원",
        "출처 표기·환각 방지를 시스템 프롬프트로 강제",
    ]),

    ("배포: 채팅 웹앱", [
        "Streamlit 채팅 UI: 과목 필터, 참고 리뷰 수 조절, 출처 펼치기",
        "Streamlit Community Cloud로 공개 URL 호스팅(GitHub 연동)",
        "API 키는 Secrets로 안전 관리(코드/깃 미저장)",
        "키 없이도 오프라인 요약으로 동작 → 누구나 즉시 사용",
    ]),

    ("데모 예시", [
        "질문: '모바일프로그래밍 학점 잘 주는 교수 추천해줘'",
        "답변(요약): 윤홍수 교수 평균 5.0/5로 가장 긍정적",
        "  (가천대 모바일프로그래밍 26년 1학기 평점 5점 리뷰 참고)",
        "이상홍 4.0 / 이수경 3.0 와 비교 제시 + 출처 자동 표기",
        "→ 학생은 3초 만에 근거 있는 수강 가이드 확보",
    ]),

    ("기대 효과 & 향후 계획", [
        "수강신청 탐색 시간 대폭 단축, 목표(학점/과제) 맞춤 수강",
        "근거(출처) 기반이라 신뢰도 높고 환각 없음",
        "확장: 과목 추가 크롤링, 강의계획서(PDF) 보강, 시험정보",
        "캠퍼스 RAG 생태계(족보·장학·학사공지)로 확장 가능",
    ]),

    ("__end__", "감사합니다", "github.com/whtjdgjs12/everytime"),
]


def style_runs(tf, size, color=NAVY, bold=False):
    for p in tf.paragraphs:
        for r in p.runs:
            r.font.name = FONT
            r.font.size = Pt(size)
            r.font.color.rgb = color
            r.font.bold = bold


def add_title_slide(prs, title, subtitle):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    box = s.shapes.add_textbox(Inches(0.7), Inches(2.0), Inches(8.6), Inches(2.0))
    tf = box.text_frame; tf.word_wrap = True
    tf.text = title
    for p in tf.paragraphs:
        p.alignment = PP_ALIGN.CENTER
        for r in p.runs:
            r.font.name = FONT; r.font.size = Pt(36); r.font.bold = True; r.font.color.rgb = NAVY
    sb = s.shapes.add_textbox(Inches(0.7), Inches(4.2), Inches(8.6), Inches(1.5))
    stf = sb.text_frame; stf.word_wrap = True; stf.text = subtitle
    for p in stf.paragraphs:
        p.alignment = PP_ALIGN.CENTER
        for r in p.runs:
            r.font.name = FONT; r.font.size = Pt(16); r.font.color.rgb = GRAY


def add_bullet_slide(prs, title, bullets):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    # 제목 바
    tb = s.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(9.0), Inches(0.9))
    ttf = tb.text_frame; ttf.text = title
    for r in ttf.paragraphs[0].runs:
        r.font.name = FONT; r.font.size = Pt(28); r.font.bold = True; r.font.color.rgb = RED
    # 본문 불릿
    body = s.shapes.add_textbox(Inches(0.7), Inches(1.5), Inches(8.8), Inches(5.2))
    btf = body.text_frame; btf.word_wrap = True
    for i, b in enumerate(bullets):
        p = btf.paragraphs[0] if i == 0 else btf.add_paragraph()
        indent = b.startswith("  ")
        p.text = ("• " + b.strip()) if not indent else ("    – " + b.strip())
        p.space_after = Pt(8)
        for r in p.runs:
            r.font.name = FONT
            r.font.size = Pt(18 if not indent else 15)
            r.font.color.rgb = NAVY if not indent else GRAY


def main():
    prs = Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(7.5)
    for item in SLIDES:
        if item[0] == "__title__":
            add_title_slide(prs, item[1], item[2])
        elif item[0] == "__end__":
            add_title_slide(prs, item[1], item[2])
        else:
            add_bullet_slide(prs, item[0], item[1])
    prs.save(OUT)
    print("저장:", OUT, "| 슬라이드", len(prs.slides._sldIdLst))


if __name__ == "__main__":
    main()
