# -*- coding: utf-8 -*-
"""
에타 강의평 RAG — 채팅 웹앱 (Streamlit)
실행:  streamlit run app.py
사전조건: store/ 생성 (python ingest.py)

- API 키 없이도 동작(오프라인 요약). 사이드바에 Claude 키를 넣으면 자동으로 품질 업그레이드.
- 키는 입력칸(password)으로만 받고 파일/깃에 저장하지 않는다.
"""
import os

import streamlit as st

import ingest
from rag_vectordb import RagService, VectorRetriever

st.set_page_config(page_title="강의평 AI 비서", page_icon="🎓", layout="centered")


@st.cache_resource
def ensure_store():
    """배포 환경엔 store/ 가 없으므로(빌드 산출물) 없으면 자동 생성."""
    if not ingest.store_exists():
        with st.spinner("최초 실행: 강의평 벡터DB 빌드 중... (수십 초)"):
            ingest.build_store("auto")
    return True


@st.cache_resource
def get_rows():
    ensure_store()
    return VectorRetriever().store.rows


@st.cache_resource
def get_service(has_key: bool):
    # has_key 가 바뀌면 캐시 무효화되어 키 반영된 서비스로 재생성
    return RagService(llm="auto")


rows = get_rows()
courses = sorted(rows[rows["source"] == "review"]["course"].unique()) \
    if "source" in rows.columns else sorted(rows["course"].unique())

def _server_key() -> str:
    """배포 환경(Streamlit Cloud)의 Secrets 에 등록한 서버 키. 모든 사용자에게 적용된다.
    secrets.toml 이 없을 때 st.secrets 에 접근하면 UI 에러가 뜨므로, 파일이 있을 때만 읽는다."""
    from pathlib import Path
    env = os.environ.get("ANTHROPIC_API_KEY", "")
    if env:
        return env
    paths = [Path.home() / ".streamlit" / "secrets.toml",
             Path.cwd() / ".streamlit" / "secrets.toml"]
    if any(p.exists() for p in paths):
        try:
            return st.secrets.get("ANTHROPIC_API_KEY", "") or ""
        except Exception:
            return ""
    return ""


server_key = _server_key()

with st.sidebar:
    st.header("⚙️ 설정")
    if server_key:
        os.environ["ANTHROPIC_API_KEY"] = server_key
        key_in = server_key
        st.success("✅ Claude 서버 키 적용됨 — 모든 답변이 Claude로 생성됩니다")
    else:
        key_in = st.text_input("Claude API 키 (선택)", type="password",
                               value=os.environ.get("ANTHROPIC_API_KEY", ""),
                               help="console.anthropic.com 에서 발급. 넣으면 답변이 자연어 AI로 업그레이드됩니다.")
        if key_in:
            os.environ["ANTHROPIC_API_KEY"] = key_in
    course = st.selectbox("과목 필터", ["(전체)"] + list(courses))
    top_k = st.slider("참고 리뷰 수", 3, 10, 5)
    st.caption("키 없으면 오프라인 요약, 키 있으면 Claude 생성")

svc = get_service(bool(key_in))
mode_label = "🟢 Claude" if key_in else "⚪ 오프라인 요약"

st.title("🎓 강의평 AI 비서")
st.caption(f"가천대 5과목 실제 강의평 기반 RAG · 현재 모드: {mode_label}")

if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

if prompt := st.chat_input("예: 확률과 통계 학점 잘 주는 교수 추천해줘"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("강의평 검색 중..."):
            course_filter = None if course == "(전체)" else course
            res = svc.answer(prompt, course=course_filter, top_k=top_k)
        st.markdown(res["answer"])
        if res.get("sources"):
            with st.expander(f"📚 출처 {len(res['sources'])}건 · 모드: {res.get('mode','')}"):
                for s in res["sources"]:
                    st.markdown(f"- **{s['professor']}** · {s['course']} · {s['citation']} "
                                f"(유사도 {s['score']})")
    st.session_state.messages.append({"role": "assistant", "content": res["answer"]})
