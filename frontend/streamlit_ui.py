import streamlit as st


HIDE_STREAMLIT_SIDEBAR_STYLE = """
<style>
    [data-testid="stSidebar"],
    [data-testid="stSidebarNav"],
    [data-testid="collapsedControl"] {
        display: none;
    }
</style>
"""


def configure_page() -> None:
    """Configure the Streamlit page and hide the auto-generated sidebar."""
    st.set_page_config(
        page_title="FinAgent-SME",
        layout="centered",
        initial_sidebar_state="collapsed",
    )
    st.markdown(HIDE_STREAMLIT_SIDEBAR_STYLE, unsafe_allow_html=True)
