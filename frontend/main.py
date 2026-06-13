import streamlit as st

from streamlit_ui import configure_page
from views import report, search

configure_page()

if "page" not in st.session_state:
    st.session_state.page = "Search"
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "base_url" not in st.session_state:
    st.session_state.base_url = "http://localhost:8000"
if "pending_job_id" not in st.session_state:
    st.session_state.pending_job_id = None
if "pending_job_status" not in st.session_state:
    st.session_state.pending_job_status = None

st.title("FinAgent-SME")

if st.session_state.page == "Search":
    search.render()
else:
    report.render()
