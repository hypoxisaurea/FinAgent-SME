import streamlit as st


HIDE_STREAMLIT_NAVIGATION_STYLE = """
<style>
    header[data-testid="stHeader"],
    [data-testid="stToolbar"],
    #MainMenu {
        display: none;
    }

    [data-testid="stSidebar"],
    [data-testid="stSidebarNav"],
    [data-testid="collapsedControl"] {
        display: none;
    }

    .block-container {
        padding-top: 1rem;
    }
</style>
"""


def configure_page() -> None:
    """Configure the Streamlit page and hide generated navigation chrome."""
    st.set_page_config(
        page_title="FinAgent-SME",
        layout="centered",
        initial_sidebar_state="collapsed",
    )
    st.markdown(HIDE_STREAMLIT_NAVIGATION_STYLE, unsafe_allow_html=True)
