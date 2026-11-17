"""Embed the reviewed HTML interface in Streamlit using the current session data."""
from __future__ import annotations
import json
import streamlit as st
import streamlit.components.v1 as components



from pathlib import Path


def _html_template():
    root = Path(__file__).resolve().parent
    html = (root / "dashboard_template.html").read_text(encoding="utf-8")
    plotly = (root / "plotly_bundle.js").read_text(encoding="utf-8")
    return html.replace("/* PLOTLY_BUNDLE */", plotly)


def compose_dashboard(full, audit, master=None):
    from routing_data import fleet_roster,QUALITY_RULES
    html=_html_template()
    marker='const RAW='
    start=html.index(marker)
    end=html.index(';let view=',start)
    def serialise(frame):
        return frame.to_json(orient='records',date_format='iso').replace('</','<\\/')
    roster=fleet_roster(master,full,full) if master is not None else None
    replacement='const RAW='+serialise(full)+',ROSTER='+(serialise(roster) if roster is not None else '[]')+',RULES='+json.dumps(QUALITY_RULES)
    html=html[:start]+replacement+html[end:]
    count=full['IMO'].nunique()
    master_count=len(master) if master is not None else count
    fleet_count=master['Fleet'].nunique() if master is not None else full['Fleet'].nunique()
    # Keep the HTML layout while replacing extraction-specific labels with real data.
    html=html.replace('80 vessels in fleet master',f'{master_count} vessels in fleet master')
    html=html.replace('10 fleets · 55 vessels with records',f'{fleet_count} fleets · {count} vessels with records')
    html=html.replace('55 vessels in extraction · 80 in master',f'{count} vessels in extraction · {master_count} in master')
    html=html.replace('16/11/2026',audit['extraction_date'].strftime('%d/%m/%Y'))
    html=html.replace('15/11/2026 19:41',audit['last_approval'].strftime('%d/%m/%Y %H:%M'))
    html=html.replace('value="01/01/2026"',f'value="{audit["first_approval"]:%d/%m/%Y}"')
    html=html.replace('value="15/11/2026"',f'value="{audit["last_approval"]:%d/%m/%Y}"')
    html=html.replace("card('WRAPPED CSV RECORDS','167'",f"card('WRAPPED CSV RECORDS','{audit['wrapped_records']}'")
    html=html.replace('Offline browser preview.<br>No login or API calls required.',
                      'Interactive Streamlit dashboard.<br>Filters run instantly in this view.')
    html=html.replace('This standalone preview uses the bundled data. The Streamlit app adds CSV replacement, fleet-mapping replacement, endpoint maps and the existing API connection test.',
                      'Data is prepared by the Python engine and displayed in this dashboard. Replace the deployed CSV files to update the source extraction or fleet mapping.')
    if master is None or not master['IMO'].eq('').any():
        html=html.replace('Istanbul Express has no IMO in the master and is categorised using its exact name.','')
    return html


def render_html_dashboard(full,audit,master=None):
    components.html(compose_dashboard(full,audit,master),height=900,scrolling=True)
