import requests
import streamlit as st


def _render_http_error(response: requests.Response) -> None:
    status_code = response.status_code
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}

    st.error(f"오케스트레이터 호출 실패 ({status_code})")
    st.json(payload)


def run_health_check() -> dict | None:
    try:
        resp = requests.get(f"{st.session_state.base_url}/api/health", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error("Health check failed")
        st.exception(e)
        return None


def run_orchestrator_search(company_name: str) -> dict | None:
    try:
        url = f"{st.session_state.base_url}/api/v1/workflows/orchestrator"
        payload = {"company_name": company_name}
        resp = requests.post(url, json=payload, timeout=300)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        if e.response is not None:
            _render_http_error(e.response)
        else:
            st.error("오케스트레이터 호출 실패")
            st.exception(e)
        return None
    except Exception as e:
        st.error("오케스트레이터 호출 실패")
        st.exception(e)
        return None


def render() -> None:

    col1, col2 = st.columns([3, 1])
    with col1:
        company_name = st.text_input("회사명", key="company_name_input")
    with col2:
        if st.button("Health 체크"):
            health = run_health_check()
            if health:
                st.success("백엔드 연결 성공")
                st.json(health)

    if st.button("검색"):
        if not company_name:
            st.warning("회사명을 입력하세요.")
        else:
            with st.spinner("오케스트레이터 실행 중..."):
                result = run_orchestrator_search(company_name)
                if result is not None:
                    st.session_state.last_result = result
                    st.session_state.page = "Report"
                    st.rerun()
