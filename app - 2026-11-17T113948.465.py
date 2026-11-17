"""Weather Routing: Python data engine, full-window HTML interface.
Run with: streamlit run app.py
"""
from pathlib import Path
import streamlit as st
import hmac
from routing_data import parse_extraction, parse_fleet_master, attach_fleets
from preview_renderer import render_html_dashboard

APP_DIR = Path(__file__).resolve().parent
SNAPSHOT = APP_DIR / '20261116_Technomar_Approved_Routes.csv'

st.set_page_config(
    page_title="Weather Routing | Technomar",
    page_icon=str(APP_DIR / "technomar.png"),
    layout="wide",
    initial_sidebar_state="collapsed",)



def require_login():
    try:
        users = dict(st.secrets["passwords"])
    except (FileNotFoundError, KeyError):
        st.error("Login is not configured. Add the [passwords] section in Streamlit Secrets.")
        st.stop()
    if not users or any(not isinstance(v, str) or not v for v in users.values()):
        st.error("Login configuration is invalid. Contact the app administrator.")
        st.stop()
    if st.session_state.get("authenticated_user") in users:
        return
    st.markdown("<style>.block-container {max-width:460px;padding-top:8vh;}</style>", unsafe_allow_html=True)
    st.image(str(APP_DIR / "technomar.png"), width=90)
    st.title("Weather Routing")
    st.caption("Technomar · Sign in to continue")
    with st.form("login"):
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Sign in", use_container_width=True)
    if submitted:
        expected = users.get(username, "")
        valid = hmac.compare_digest(password.encode(), expected.encode())
        if expected and valid:
            st.session_state["authenticated_user"] = username
            del st.session_state["login_password"]
            del st.session_state["login_username"]
            st.rerun()
        st.error("Incorrect username or password.")
    st.stop()


@st.cache_data(show_spinner=False)
def load_dashboard(extraction,filename,fleet):
    full,audit=parse_extraction(extraction,filename)
    master=parse_fleet_master(fleet)
    return attach_fleets(full,master),audit,master


def main():
    require_login()
    st.markdown('''<style>
    html,body {margin:0!important;padding:0!important;overflow:hidden!important;}
    .stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"] {
        background:#f3f6f7;margin:0!important;padding:0!important;}
    [data-testid="stHeader"],[data-testid="stToolbar"],
    [data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"],[data-testid="stDecoration"],footer {display:none!important;}
    .block-container,[data-testid="stMainBlockContainer"] {
        max-width:none!important;width:100%!important;padding:0!important;margin:0!important;}
    iframe {position:fixed!important;inset:0!important;width:100vw!important;
        height:100vh!important;height:100dvh!important;border:0!important;
        margin:0!important;display:block!important;z-index:100;}
    [data-testid="stIFrame"] {margin:0!important;padding:0!important;}
    </style>''',unsafe_allow_html=True)
    
    try:
        full,audit,master=load_dashboard(SNAPSHOT.read_bytes(),SNAPSHOT.name,
                                         (APP_DIR/'Fleet.csv').read_bytes())
        if full['Approval timestamp (UTC)'].notna().sum()==0:
            raise ValueError('No valid approval timestamps are available in the extraction.')
    except (OSError,ValueError,UnicodeError) as exc:
        st.error('Unable to load dashboard data: '+str(exc))
        return
    render_html_dashboard(full,audit,master)


if __name__=='__main__':
    main()
