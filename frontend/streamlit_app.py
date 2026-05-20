import streamlit as st

st.set_page_config(page_title="FinAgent-SME (Streamlit)", layout="centered")

if "page" not in st.session_state:
    st.session_state.page = "Search"
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "base_url" not in st.session_state:
    st.session_state.base_url = "http://localhost:8000"

st.title("FinAgent-SME — Streamlit UI")
from pages import search, report


# Top controls
cols = st.columns([1, 1, 3])
with cols[0]:
    if st.button("Search"):
        st.session_state.page = "Search"
with cols[1]:
    if st.button("Report"):
        st.session_state.page = "Report"
with cols[2]:
    st.session_state.base_url = st.text_input("Backend Base URL", value=st.session_state.base_url)


if st.session_state.page == "Search":
    search.render()
else:
    report.render()
