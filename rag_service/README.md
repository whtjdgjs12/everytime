# 에브리타임 강의평 RAG AI 서비스

`project_proposal.md` 기획서를 구현한 RAG 서비스입니다. **두 가지 버전**이 있습니다.

| 버전 | 데이터 | 검색 방식 | 진입점 |
|------|--------|-----------|--------|
| **v2 (실제 데이터·벡터DB)** ⭐ | 실제 크롤링 강의평 **995건** | **벡터 임베딩 의미검색** (벡터DB) | `rag_vectordb.py` |
| v1 (PoC·모의 데이터) | 모의 29건(8스키마) | TF-IDF 유사도 | `rag_service.py` |

아래는 **v2(실제 데이터 벡터DB RAG)** 기준 설명입니다.

## 파이프라인 (velog RAG 구조)

```
[6개 학교 CSV]                                  ← 원본 (evrytime-emotion-prediction-master/data)
   │ build_dataset.py  (통합·정제·중복제거)
   ▼
reviews_real.csv  (995건: id,school,professor,course,rating,review)
   │ ingest.py  (임베딩 → 벡터DB 적재 = '인덱싱')
   ▼
store/  벡터 저장소 (vectors.npy + rows.csv + lsa_model.pkl)
   │
   ▼  ── 질문 ──▶ rag_vectordb.py
        ① 임베딩  ② 벡터 의미검색(+필터)  ③ 프롬프트(출처/환각방지)  ④ 생성
```

## 실행 방법

필요 패키지: `pandas`, `scikit-learn`, `numpy` (설치돼 있음)

```bash
# 1) 데이터 빌드 (원본 6개 CSV → 정제 통합)
python build_dataset.py

# 2) 인덱싱 (임베딩 → 벡터DB 적재)  ※ store/ 생성
python ingest.py

# 3) 테스트 (검색/필터/출처/환각방지 + 실제 교수 데모)
python test_vectordb.py

# 4) 질의
python rag_vectordb.py "컴퓨터프로그래밍 꿀강 추천" -c 컴퓨터프로그래밍
python rag_vectordb.py "이 교수 수업 어때?" -p 윤승태
python rag_vectordb.py            # 대화형
```
옵션: `-p 교수명`, `-c 과목명`, `-s 학교명`, `-k 개수`

> 팀원은 저장소를 clone 한 뒤 **1)→2)** 만 실행하면 `store/`(벡터DB)가 생성되어 바로 사용 가능합니다. (`store/`는 용량이 커서 git에 포함하지 않고 재생성합니다.)

## 임베딩 백엔드 (2종, 키 유무로 자동 전환)

| 백엔드 | 설명 | 조건 |
|--------|------|------|
| **LSA** (기본) | TF-IDF + SVD 잠재의미 임베딩. 순수 sklearn, 오프라인, 비용 0 | 기본값 |
| **Gemini** | `text-embedding-004` 트랜스포머 임베딩 (진짜 의미) | `GEMINI_API_KEY` 설정 시 |

```bash
# Gemini 임베딩으로 더 정확한 의미검색 (키 필요)
GEMINI_API_KEY=... python ingest.py --backend gemini
GEMINI_API_KEY=... python rag_vectordb.py "꿀강 추천" -c 컴퓨터프로그래밍
```
생성(답변 문장)도 `GEMINI_API_KEY` 가 있으면 Gemini, 없으면 규칙기반 오프라인 요약으로 동작합니다.

## 요구사항 매핑 (기획서 3.1~3.4)

| 요구사항 | 구현 |
|----------|------|
| 3.1 의미 검색 top-k | `VectorRetriever.retrieve` (벡터 코사인 최근접) |
| 3.2 교수/과목/학교 필터 | 메타데이터로 후보 제한 후 검색 |
| 3.3 출처 표기 | `(강대 컴퓨터프로그래밍 평점 5점 리뷰 참고)` — 실제 데이터에 학기가 없어 학교/과목/평점으로 표기 |
| 3.4 환각 방지 | 일치 데이터 없으면 `"데이터가 준비되지 않아..."` 거부 |

## 데이터 관련 메모

- 원본 6개 CSV(각 199건) 중 **`한성에타.csv` 는 `광운에타.csv` 와 199건 전부 동일**(크롤링 중복)하여 통합 시 자동 제거 → **최종 995건**.
- 실제 데이터에는 수강학기·과제부담·시험유형 컬럼이 없어, 출처 표기는 존재하는 값(학교·과목·평점)으로 구성했습니다.

## 파일 구성

| 파일 | 역할 |
|------|------|
| `build_dataset.py` | 6개 학교 CSV 통합·정제 → `reviews_real.csv` |
| `embeddings.py` | 임베딩 백엔드 (LSA / Gemini) |
| `vectorstore.py` | 경량 벡터 저장소 (numpy 영속 + 코사인 검색) |
| `ingest.py` | 임베딩 → 벡터DB 적재 |
| `rag_vectordb.py` | 벡터 RAG 서비스 (검색+생성) ⭐ |
| `test_vectordb.py` | 검증 테스트 |
| `reviews_real.csv` | 정제된 실제 강의평 995건 |
| `rag_service.py`, `reviews.csv`, `test_rag.py` | v1 (모의 데이터 PoC) |

## 참고: ChromaDB 대신 numpy 저장소를 쓴 이유

처음에는 velog 글처럼 ChromaDB 를 사용하려 했으나, 현재 PC 환경에서 ChromaDB·onnxruntime·torch 의 **네이티브 확장(DLL)이 모두 초기화 실패/세그폴트**가 발생했습니다. 그래서 동일한 벡터DB 개념(임베딩 저장 → 코사인 최근접 → 메타 필터 → 영속화)을 **네이티브 의존성 없는 순수 numpy** 로 구현했습니다. 인터페이스가 동일해, 환경이 정상화되면 `vectorstore.py` 만 Chroma 로 교체하면 됩니다.
