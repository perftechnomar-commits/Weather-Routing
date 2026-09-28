"""Run with: python -m streamlit run app.py"""
import csv
import io
import json
import streamlit as st
from marorka_client import APIError, MarorkaClient, fetch_fleet, parse_fleet

st.set_page_config(page_title='Marorka Passage Plan Test', layout='wide')
st.title('Marorka Weather Routing — connection test')
st.caption('Diagnostic build 2 — response values are hidden.')
st.write('First test login. Then retrieve one vessel or upload a fleet CSV.')
st.caption('Credentials and tokens are not included in downloads or cached. Raw plan data is preserved without assuming its schema.')

try:
    saved = dict(st.secrets.get('marorka', {}))
except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
    saved = {}
use_secrets = bool(saved.get('username') and saved.get('password'))
with st.form('connection', clear_on_submit=True):
    if use_secrets:
        st.info('Using credentials configured in Streamlit Secrets.')
        username, password = saved['username'], saved['password']
    else:
        username = st.text_input('Weather Routing API username')
        password = st.text_input('Weather Routing API password', type='password')
    mode = st.selectbox('Action', ['Test authentication only', 'Retrieve one vessel', 'Retrieve fleet CSV'])
    imo = st.text_input('IMO — for one-vessel retrieval', placeholder='Seven digits')
    fleet = st.file_uploader('Fleet CSV — columns ShipName and IMONo', type=['csv'])
    submitted = st.form_submit_button('Run test')

if submitted:
    st.session_state.pop('results', None)
    st.session_state.pop('auth_diagnostics', None)
    try:
        rows = []
        if mode == 'Retrieve one vessel':
            if len(imo.strip()) != 7 or not imo.strip().isascii() or not imo.strip().isdigit():
                raise ValueError('Enter a seven-digit IMO.')
            rows = [{'ShipName': '', 'IMONo': imo.strip()}]
        elif mode == 'Retrieve fleet CSV':
            if fleet is None:
                raise ValueError('Upload a fleet CSV first.')
            rows = parse_fleet(fleet.getvalue().decode('utf-8-sig'))
        with MarorkaClient(username, password) as client:
            with st.spinner('Requesting access token…'):
                client.authenticate()
            st.session_state['auth_diagnostics'] = client.auth_diagnostics
            st.success('Token generation succeeded. Token is kept private.')
            if rows:
                bar = st.progress(0.0)
                results = fetch_fleet(client, rows, lambda n, total: bar.progress(n / total))
                st.session_state['results'] = results
    except (APIError, ValueError) as exc:
        st.error(str(exc))
        if isinstance(exc, APIError) and exc.diagnostics:
            st.session_state['auth_diagnostics'] = exc.diagnostics
    finally:
        password = None

diagnostics = st.session_state.get('auth_diagnostics')
if diagnostics:
    with st.expander('Safe authentication diagnostics', expanded=True):
        st.caption('Share this report to investigate the response format. It contains no response values, credentials, tokens, cookies, or headers.')
        st.json(diagnostics)
        st.download_button('Download safe authentication diagnostics',
                           json.dumps(diagnostics, indent=2),
                           'marorka_auth_diagnostics.json', 'application/json')

results = st.session_state.get('results')
if results:
    summary = [{k: v for k, v in row.items() if k != 'Plan'} for row in results]
    st.dataframe(summary, use_container_width=True)
    st.download_button('Download plans and statuses (JSON)', json.dumps(results, ensure_ascii=False, indent=2),
                       'marorka_passage_plans.json', 'application/json')
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=['ShipName', 'IMONo', 'Status', 'HTTPStatus', 'Error'])
    writer.writeheader()
    for row in summary:
        # Protect spreadsheet consumers against formula-like server text.
        writer.writerow({k: ("'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v) for k, v in row.items()})
    st.download_button('Download status table (CSV)', output.getvalue(), 'marorka_status.csv', 'text/csv')
    index = st.selectbox('Inspect a vessel response', range(len(results)),
                         format_func=lambda i: f"{results[i]['ShipName']} — {results[i]['IMONo']}")
    st.json(results[index]['Plan'])
