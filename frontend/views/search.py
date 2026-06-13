import time

import requests
import streamlit as st


def _render_http_error(response: requests.Response) -> None:
    status_code = response.status_code
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}

    st.error(f"워크플로우 호출 실패 ({status_code})")
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


def submit_workflow_job(company_name: str) -> dict | None:
    try:
        url = f"{st.session_state.base_url}/api/v1/workflows/jobs"
        payload = {"company_name": company_name}
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        if e.response is not None:
            _render_http_error(e.response)
        else:
            st.error("워크플로우 job 생성 실패")
            st.exception(e)
        return None
    except Exception as e:
        st.error("워크플로우 job 생성 실패")
        st.exception(e)
        return None


def get_workflow_job_status(job_id: str) -> dict | None:
    try:
        url = f"{st.session_state.base_url}/api/v1/workflows/jobs/{job_id}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        if e.response is not None:
            _render_http_error(e.response)
        else:
            st.error("워크플로우 job 상태 조회 실패")
            st.exception(e)
        return None
    except Exception as e:
        st.error("워크플로우 job 상태 조회 실패")
        st.exception(e)
        return None


def get_workflow_job_result(job_id: str) -> dict | None:
    try:
        url = f"{st.session_state.base_url}/api/v1/workflows/jobs/{job_id}/result"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        if e.response is not None:
            _render_http_error(e.response)
        else:
            st.error("워크플로우 job 결과 조회 실패")
            st.exception(e)
        return None
    except Exception as e:
        st.error("워크플로우 job 결과 조회 실패")
        st.exception(e)
        return None


def _render_job_progress() -> None:
    job_id = st.session_state.pending_job_id
    if not job_id:
        return

    status_payload = get_workflow_job_status(job_id)
    if status_payload is None:
        return

    st.session_state.pending_job_status = status_payload
    status = status_payload.get("status", "queued")
    company_name = status_payload.get("company_name", "-")
    step_summary = status_payload.get("step_summary") or {}

    st.info(
        f"심사 진행 중: `{company_name}` / job `{job_id}` / 상태 `{status}`"
    )
    if step_summary:
        st.json(step_summary)

    if status == "succeeded":
        result = get_workflow_job_result(job_id)
        if result is not None:
            st.session_state.last_result = result
            st.session_state.pending_job_id = None
            st.session_state.pending_job_status = None
            st.session_state.page = "Report"
            st.rerun()
        return

    if status == "failed":
        st.error("심사 작업이 실패했습니다. 상태 정보를 확인해주세요.")
        st.json(status_payload)
        st.session_state.pending_job_id = None
        return

    st.caption("2초 후 상태를 다시 확인합니다.")
    time.sleep(2)
    st.rerun()


def render() -> None:
    if st.session_state.pending_job_id:
        _render_job_progress()
        return

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
            with st.spinner("심사 작업 접수 중..."):
                job = submit_workflow_job(company_name)
                if job is not None:
                    st.session_state.pending_job_id = job["job_id"]
                    st.session_state.pending_job_status = job
                    st.rerun()
