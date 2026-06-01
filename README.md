# everytime — 강의평 RAG 수강신청 AI 비서

우리 학교(가천대) **5과목의 실제 강의평을 직접 수집**해, 자연어 한 줄로 **근거(출처)와 함께**
수강 추천을 받는 **RAG 채팅 웹앱**입니다.

> 대상 과목: 확률과 통계 · 모바일프로그래밍 · 빅데이터분석개론 · 스마트기기시스템 · 블록체인개론 (강의평 187건)

## 구성

| 경로 | 내용 |
|------|------|
| `rag_service/` | 크롤러 · 벡터RAG · Claude 생성 · Streamlit 웹앱 |
| `presentation/` | 발표자료(PPTX) · 발표대본 |
| `process.md` | 전체 진행 흐름 (대학생 눈높이) |
| `project_proposal.md` | 서비스 기획서 |

## 빠른 시작

```bash
cd rag_service

# (선택) 직접 크롤링 — 본인 계정·책임. 에타 약관 주의.
#   $env:EVERYTIME_ID / $env:EVERYTIME_PW 설정 후
python everytime_crawler.py --delay 3

python ingest.py                 # 임베딩 → 벡터DB
python -m streamlit run app.py   # 채팅 웹앱 (http://localhost:8501)
```

`ANTHROPIC_API_KEY` 를 설정하면 답변이 **Claude**로, 없으면 규칙기반 오프라인 요약으로 동작합니다.

## 파이프라인

```
에타 강의평 ──크롤러(Playwright)──▶ reviews_real.csv(187건)
            ──임베딩(LSA)──▶ 벡터 저장소(numpy) ──RAG──▶ Streamlit 채팅앱
                                  검색+필터+출처표기+환각방지 / Claude 생성
```

## 요구사항 구현 (기획서 3.1~3.4)
- 3.1 의미 검색 top-k (코사인 최근접)
- 3.2 교수/과목 속성 필터
- 3.3 출처 표기 — `(가천대 모바일프로그래밍 26년 1학기 평점 5점 리뷰 참고)`
- 3.4 환각 방지 / 답변 거부

자세한 사용법: [`rag_service/README.md`](rag_service/README.md) · 진행 과정: [`process.md`](process.md)

## 배포
Streamlit Community Cloud로 공개 URL 호스팅 (GitHub 연동, main 파일 `rag_service/app.py`).
API 키는 Secrets로 관리합니다.

---
🤖 참고: 일부 코드/문서는 Claude Code로 작성되었습니다.
