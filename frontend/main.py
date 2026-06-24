import streamlit as st

try:
    from config import get_backend_url
    from streamlit_ui import configure_page
    from views import report, search
except ModuleNotFoundError:  # pragma: no cover - package import fallback
    from frontend.config import get_backend_url
    from frontend.streamlit_ui import configure_page
    from frontend.views import report, search

configure_page()

if "page" not in st.session_state:
    st.session_state.page = "Search"
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "base_url" not in st.session_state:
    st.session_state.base_url = get_backend_url()
if "pending_job_id" not in st.session_state:
    st.session_state.pending_job_id = None
if "pending_job_status" not in st.session_state:
    st.session_state.pending_job_status = None
if "submitting_company_name" not in st.session_state:
    st.session_state.submitting_company_name = None

st.title("FinAgent-SME")

if st.session_state.page == "Search":
    search.render()
else:
    report.render()
