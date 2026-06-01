# everytime — 에브리타임 강의평 RAG / 감정분석 프로젝트

에브리타임 강의평 데이터를 활용한 두 가지 작업을 담은 저장소입니다.

## 구성

| 경로 | 내용 |
|------|------|
| `project_proposal.md` | 교수 리뷰 RAG AI 분석 서비스 **기획서** |
| `rag_service/` | 기획서를 구현한 **RAG AI 서비스 PoC** (코드·모의데이터·테스트) |
| `evrytime-emotion-prediction-master/` | 강의평 **감정분석** 참고 프로젝트 (크롤링 + Naive Bayes) |
| `temp_pdf/` | 강의계획서 PDF 자료 |

## RAG 서비스 빠른 시작

```bash
cd rag_service
python test_rag.py                                   # 전 기능 자동 검증 (API 키 불필요)
python rag_service.py "운영체제 꿀강 추천" -c 운영체제   # 단발 질의
```

자세한 사용법은 [`rag_service/README.md`](rag_service/README.md) 참고.

## 요구사항 구현 (기획서 3.1~3.4)

- 3.1 자연어 의미 검색 top-3 (TF-IDF 코사인)
- 3.2 교수/과목 속성 필터
- 3.3 출처 표기 (Strict Grounding) — `(2025년 2학기 평점 5점 리뷰 참고)`
- 3.4 환각 방지 / 답변 거부 (Zero-Hallucination)

`GEMINI_API_KEY` 설정 시 생성 단계가 Gemini API로 동작하며, 없으면 오프라인 폴백으로 전체 파이프라인이 검증됩니다.
