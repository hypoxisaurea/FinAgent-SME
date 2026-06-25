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
        padding-top: 1.25rem;
    }

    .app-shell-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 24px;
        padding: 14px 18px;
        margin-bottom: 10px;
        background: rgba(255, 255, 255, 0.72);
        border: 1px solid rgba(195, 213, 232, 0.72);
        border-radius: 8px;
        box-shadow: 0 14px 30px rgba(31, 78, 121, 0.08);
        backdrop-filter: blur(12px);
    }

    .app-brand {
        color: #0b2f5f;
        font-size: 1.05rem;
        font-weight: 800;
        letter-spacing: 0;
    }

    .app-subtitle {
        color: #64748b;
        font-size: 0.82rem;
        font-weight: 600;
        margin-top: 4px;
    }

    .app-status {
        color: #ffffff;
        background: linear-gradient(135deg, #1157a8 0%, #1784d8 100%);
        border: 1px solid rgba(255, 255, 255, 0.28);
        border-radius: 999px;
        padding: 8px 12px;
        font-size: 0.78rem;
        font-weight: 800;
        white-space: nowrap;
        box-shadow: 0 10px 20px rgba(17, 87, 168, 0.18);
    }

    @media (max-width: 720px) {
        .app-shell-header {
            align-items: flex-start;
            flex-direction: column;
            gap: 10px;
        }
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
