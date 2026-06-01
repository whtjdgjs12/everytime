# 에브리타임 교수 리뷰 RAG AI 분석 서비스 (PoC)

`project_proposal.md` 기획서를 실제 동작하는 코드로 구현한 PoC입니다.
강의평 데이터를 근거로, 자연어 질문 한 줄에 맞춤형 수강 추천을 출처 표기와 함께 제공합니다.

## 구성

| 파일 | 설명 |
|------|------|
| `reviews.csv` | 컴퓨터공학과 교수 5명 / 29개 모의 강의평 (기획서 4.1) — 8개 스키마 |
| `rag_service.py` | RAG 엔진 (검색 + 필터 + 출처표기 + 환각방지 + 생성) |
| `test_rag.py` | 요구사항 3.1~3.4 및 페르소나 시나리오 자동 검증 |

### reviews.csv 8개 스키마
`id, professor(교수명), course(과목명), semester(수강학기), rating(평점 1~5), assignment_load(과제부담), exam_type(시험유형), review(강의평 본문)`

## 기획서 요구사항 ↔ 구현 매핑

| 요구사항 | 구현 위치 |
|----------|-----------|
| 3.1 자연어 의미 검색 top-3 | `RagRetriever.retrieve` (TF-IDF 코사인 유사도) |
| 3.2 교수/과목 속성 필터 | `retrieve(professor=, course=)` |
| 3.3 출처 표기 (Strict Grounding) | `Review.citation` → `(2025년 2학기 평점 5점 리뷰 참고)` |
| 3.4 환각 방지 / 답변 거부 | `RagService.answer` → 데이터 없으면 거부 메시지 |

## 실행 방법

필요 패키지: `pandas`, `scikit-learn` (이미 설치됨)

```bash
# 1) 자동 테스트 (API 키 없이 전 기능 검증)
python test_rag.py

# 2) 단발 질의 (JSON 출력)
python rag_service.py "학점 3.5 목표인데 컴퓨터네트워크 홍길동 vs 박민수 누가 유리해?" -c 컴퓨터네트워크 -k 6

# 3) 대화형 모드
python rag_service.py
```

## Gemini 연동

`GEMINI_API_KEY` 환경변수를 설정하면 생성 단계가 Gemini REST API로 동작합니다.
키가 없으면 검색 결과를 규칙 기반으로 요약하는 **오프라인 폴백**으로 동작하여,
API 키 없이도 전체 파이프라인을 테스트할 수 있습니다.

```powershell
$env:GEMINI_API_KEY = "발급받은_키"
python rag_service.py "운영체제 꿀강 추천" -c 운영체제
```

## 참고

- 의미 임베딩은 오프라인 검증을 위해 문자 n-gram TF-IDF를 사용합니다.
  운영 단계에서는 동일 인터페이스로 Gemini `text-embedding` 으로 교체 가능합니다.
- `temp_pdf/`의 강의계획서 PDF는 커스텀 CID 폰트로 인코딩되어 텍스트 추출이 불가하며,
  기획서가 PoC 단계에 모의 데이터 사용을 명시하므로 본 PoC에는 포함하지 않았습니다.
- 상위 디렉터리의 `evrytime-emotion-prediction-master`는 동일 도메인(에타 강의평)의
  감정분석 참고 프로젝트로, 본 RAG 서비스의 데이터 도메인 근거로 참고했습니다.
