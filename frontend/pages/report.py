import json
import streamlit as st
import pandas as pd


def render() -> None:
    st.header("2) 심사 결과 리포트")
    if not st.session_state.last_result:
        st.info("표시할 결과가 없습니다. 먼저 검색 페이지에서 심사를 실행하세요.")
        return

    result = st.session_state.last_result
    st.subheader("원본 JSON")
    st.json(result)

    # If result contains tabular sections, try to display them
    if isinstance(result, dict):
        # Show top-level key/value table for simple items
        simple_items = {k: v for k, v in result.items() if not isinstance(v, (list, dict))}
        if simple_items:
            st.subheader("요약")
            df = pd.DataFrame(list(simple_items.items()), columns=["키", "값"])
            st.table(df)

        # Show any list/dict sections as tables
        for k, v in result.items():
            if isinstance(v, list):
                st.subheader(k)
                try:
                    st.dataframe(pd.DataFrame(v))
                except Exception:
                    st.write(v)
            elif isinstance(v, dict) and k != "detail":
                st.subheader(k)
                try:
                    st.json(v)
                except Exception:
                    st.write(v)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.download_button("JSON 다운로드", data=json.dumps(result, ensure_ascii=False, indent=2), file_name="credit_assessment_result.json", mime="application/json")
    with col2:
        if st.button("다시 검색 페이지로 이동"):
            st.session_state.page = "Search"
