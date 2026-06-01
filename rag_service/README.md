# 에브리타임 강의평 RAG AI 서비스

`project_proposal.md` 기획서를 구현한 RAG 서비스입니다.

**최종 데이터: 가천대 5과목 실제 강의평 187건** (직접 크롤링).
대상 과목: 확률과 통계 · 모바일프로그래밍 · 빅데이터분석개론 · 스마트기기시스템 · 블록체인개론.

| 진입점 | 역할 |
|--------|------|
| `everytime_crawler.py` | 강의평 크롤러(Playwright) → `reviews_real.csv` |
| `ingest.py` | 임베딩 → 벡터 저장소(`store/`) |
| `rag_vectordb.py` | 벡터 RAG (검색·필터·출처표기·환각방지·Claude/오프라인 생성) ⭐ |
| `app.py` | Streamlit 채팅 웹앱 |

> 채팅앱: `python -m streamlit run app.py` · Claude 켜기: `ANTHROPIC_API_KEY` 설정
> 아래는 RAG 파이프라인 상세 설명입니다.

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

필요 패키지: `pandas`, `scikit-learn`, `numpy`, `pdfminer.six`(계획서용)

```bash
# 1) 강의평 데이터 빌드 (원본 6개 CSV → 정제 통합)
python build_dataset.py

# 1-2) 강의계획서 PDF 벡터화 (선택, ../temp_pdf/*.pdf → syllabi.csv)
python build_syllabi.py

# 2) 인덱싱 (리뷰+계획서 임베딩 → 벡터DB 적재)  ※ store/ 생성
python ingest.py

# 3) 테스트 (검색/필터/출처/환각방지 + 계획서 + 실제 교수 데모)
python test_vectordb.py

# 4) 질의
python rag_vectordb.py "컴퓨터프로그래밍 꿀강 추천" -c 컴퓨터프로그래밍
python rag_vectordb.py "이 교수 수업 어때?" -p 윤승태
python rag_vectordb.py "수업 목표랑 평가 비중" --source syllabus   # 계획서만 검색
python rag_vectordb.py            # 대화형
```
옵션: `-p 교수명`, `-c 과목명`, `-s 학교명`, `--source review|syllabus`, `-k 개수`

### 강의계획서(PDF) 보강 — `build_syllabi.py`
`../temp_pdf/*.pdf` 를 pdfminer.six 로 추출 → **동일 내용 중복 제거** → 450자 청킹 →
리뷰와 같은 스키마(`source="syllabus"`, `rating=-1`)로 `syllabi.csv` 생성. `ingest.py` 가
리뷰와 함께 한 벡터스토어에 적재하여, 한 질문이 리뷰·계획서를 함께 근거로 쓴다.
출처는 `(학교 과목 강의계획서 참고)` 로 구분 표기된다.

> ⚠️ 현재 `temp_pdf/` 의 81개 PDF 는 **모두 동일한 '가천인세미나' 계획서 1종**(나머지 80개는 중복)이라
> 실질 보강 효과는 제한적이다. **서로 다른 실제 강의계획서 PDF 를 `temp_pdf/` 에 넣고 위 1-2)→2) 만
> 다시 실행**하면 그대로 보강된다.

> 팀원은 저장소를 clone 한 뒤 **1)→2)** 만 실행하면 `store/`(벡터DB)가 생성되어 바로 사용 가능합니다. (`store/`는 용량이 커서 git에 포함하지 않고 재생성합니다.)

## 우리학교 실제 데이터 직접 수집 — 크롤러 (`everytime_crawler.py`)

지정한 5과목(확률과 통계·모바일프로그래밍·빅데이터분석개론·스마트기기시스템·블록체인개론)의
강의평을 에타에서 수집해 `reviews_real.csv` 로 저장한다. 이후 `ingest.py` 부터 동일.

> ⚠️ **경고:** 에브리타임 약관은 자동 수집을 금지하며, 적발 시 **계정 영구 정지/IP 차단** 위험이
> 있다(기획서 4.2도 경고). 실행 책임은 전적으로 실행자 본인에게 있다. 계정은 코드에 넣지 말고
> 환경변수로 전달하며, 요청 간 지연(`--delay`)을 충분히 둔다.

```powershell
# 1) 계정을 환경변수로 (코드/깃에 저장 금지)
$env:EVERYTIME_ID="아이디"; $env:EVERYTIME_PW="비밀번호"

# 2) 크롤 (기본 headed — 캡차/2단계 인증 직접 처리)
python everytime_crawler.py                       # 5과목
python everytime_crawler.py --courses "블록체인개론" --delay 3

# 3) 이후 파이프라인 동일
python ingest.py
python rag_vectordb.py "블록체인개론 꿀강 추천" -c 블록체인개론
```

**셀렉터를 못 찾으면?** → `debug/` 에 **스크린샷(.png)+DOM 덤프(.html)** 가 자동 저장된다.
그 파일로 실제 구조를 보고 `everytime_crawler.py` 상단 `SELECTORS` 를 수정하면 된다.
(에타 DOM 은 학교/시점에 따라 다르므로 셀렉터 조정이 필요할 수 있다.)

**오프라인 검증:** `python test_crawler_offline.py` — 접속 없이 파싱·평점추출·CSV연동·캡처폴백을
픽스처로 검증(18개 통과). 실제 로그인 크롤은 본인이 실행한다.

관련 파일: `everytime_crawler.py`(크롤러), `ev_parse.py`(파싱 헬퍼), `test_crawler_offline.py`(테스트).

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
