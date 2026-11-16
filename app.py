"""Weather Routing review dashboard. Run: streamlit run app.py"""
from __future__ import annotations
from datetime import date, timedelta
from html import escape
from pathlib import Path
import io
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from routing_data import (parse_extraction, quality_summary, route_catalog, safe_csv,
                          QUALITY_RULES, REQUIRED_COLUMNS, parse_fleet_master, attach_fleets, fleet_roster)

APP_DIR = Path(__file__).resolve().parent
SNAPSHOT = APP_DIR / '20261116_Technomar_Approved_Routes.csv'
TEAL = '#007f80'
NAVY = '#102e3b'
GOLD = '#d4a64b'
PALETTE = [TEAL, GOLD, '#54799b', '#a67885', '#89aaa1']

st.set_page_config(page_title='Weather Routing | Technomar', page_icon='🧭', layout='wide', initial_sidebar_state='expanded')
st.markdown('''<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
html,body,[class*="css"],.stApp {font-family:'DM Sans',sans-serif;}
.stApp {background:#f4f7f8;color:#17333e;}
.block-container {padding-top:1.5rem;padding-bottom:3rem;max-width:1550px;}
[data-testid="stSidebar"] {background:#102e3b;}
[data-testid="stSidebar"] * {color:#e2edef;}
[data-testid="stSidebar"] input,[data-testid="stSidebar"] [data-baseweb="select"] * {color:#17333e;}
[data-testid="stSidebar"] [data-baseweb="select"] {background:white;border-radius:7px;}
[data-testid="stSidebar"] [data-testid="stFileUploader"] * {color:#17333e;}
[data-testid="stSidebar"] [data-testid="stFileUploader"] {background:#e9f0f2;border-radius:8px;padding:3px;}
.hero {background:linear-gradient(110deg,#102e3b 0%,#174854 65%,#16666b 100%);padding:28px 32px;border-radius:14px;color:white;margin:0 0 22px;}
.hero .eyebrow {font-size:11px;letter-spacing:2.5px;color:#a5d1d1;font-weight:700;}
.hero h1 {color:white;font-size:34px;font-weight:600;letter-spacing:-1px;margin:7px 0 8px;}
.hero p {color:#c2d9dd;font-size:14px;margin:0;}
.hero .tag {float:right;color:#c4e8df;font-size:12px;padding-top:8px;}
.kpi {background:white;border:1px solid #dfE7e9;border-top:3px solid #007f80;border-radius:10px;padding:17px 20px;min-height:120px;}
.kpi .label {color:#58717c;font-size:12px;font-weight:600;}
.kpi .value {font-size:33px;color:#102e3b;font-weight:700;line-height:1.45;}
.kpi .detail {font-size:11px;color:#71868d;}
.note {background:#edf5f5;border-left:3px solid #168b87;padding:12px 16px;font-size:13px;color:#31565f;border-radius:0 6px 6px 0;margin:16px 0;}
.section-title {font-size:21px;font-weight:600;color:#17333e;margin:20px 0 3px;}
.section-subtitle {font-size:13px;color:#6d818a;margin-bottom:10px;}
[data-testid="stRadio"] {padding:3px 0 10px;}
[data-testid="stDataFrame"] {background:white;border-radius:8px;}
footer {visibility:hidden;}
</style>''', unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_data(payload, filename):
    return parse_extraction(payload, filename)


def date_text(value):
    return '—' if pd.isna(value) else pd.Timestamp(value).strftime('%d/%m/%Y %H:%M')


def number(value, decimals=0):
    return '—' if pd.isna(value) else f'{value:,.{decimals}f}'


def section(title, subtitle=''):
    st.markdown(f'<div class="section-title">{escape(title)}</div><div class="section-subtitle">{escape(subtitle)}</div>', unsafe_allow_html=True)


def cards(items):
    for col,(label,value,detail) in zip(st.columns(len(items)),items):
        col.markdown(f'<div class="kpi"><div class="label">{escape(label)}</div><div class="value">{escape(str(value))}</div><div class="detail">{escape(detail)}</div></div>', unsafe_allow_html=True)


def chart(fig, height=345, key=None):
    fig.update_layout(template='plotly_white', height=height, font=dict(family='DM Sans, sans-serif',color='#31515d',size=12),
        paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',margin=dict(l=10,r=15,t=20,b=15),
        legend=dict(orientation='h',y=1.12,x=0),hoverlabel=dict(bgcolor='white'),
        modebar=dict(bgcolor='rgba(0,0,0,0)'))
    fig.update_xaxes(showgrid=False,zeroline=False)
    fig.update_yaxes(gridcolor='#e4ecef',zeroline=False)
    st.plotly_chart(fig,use_container_width=True,key=key,config={'displaylogo':False,'scrollZoom':False})


def table(df, key=None, height=None):
    view=df.copy()
    configs={}
    for col in view:
        if pd.api.types.is_datetime64_any_dtype(view[col]):
            configs[col]=st.column_config.DatetimeColumn(col,format='DD/MM/YYYY HH:mm')
        elif pd.api.types.is_float_dtype(view[col]):
            configs[col]=st.column_config.NumberColumn(col,format='%.2f')
    args=dict(use_container_width=True,hide_index=True,column_config=configs,key=key)
    if height:args['height']=height
    st.dataframe(view,**args)


def download(df, filename, key):
    st.download_button('Download this table · CSV',safe_csv(df),file_name=filename,mime='text/csv',key=key)


def public(df):
    return df[[col for col in df if not col.startswith('_')]]


def vessel_summary(df):
    grouped=df.groupby(['IMO','Vessel name'],dropna=False)
    summary=grouped.agg(**{'Approval events':('_plan_key','size'),'Unique plans':('_plan_key','nunique'),
        'Routes':('_route_key','nunique'),'Latest approval':('Approval timestamp (UTC)','max'),
        'Reapprovals':('Reapproval event','sum')}).reset_index()
    if 'Fleet' in df:
        mapping=df.drop_duplicates('IMO').set_index('IMO')['Fleet']
        summary.insert(2,'Fleet',summary['IMO'].map(mapping))
    return summary.sort_values('Approval events',ascending=False)


def render_overview(filtered, full, start, end, master=None, fleet_choice='All fleets'):
    cards([
        ('VESSELS IN SELECTION',number(filtered['IMO'].nunique()),f'of {full["IMO"].nunique()} vessels in the extraction'),
        ('ROUTE IDS',number(filtered['_route_key'].nunique()),'Distinct routes · not confirmed voyage count'),
        ('UNIQUE APPROVED PLANS',number(filtered['_plan_key'].nunique()),'One plan may be approved more than once'),
        ('APPROVAL EVENTS',number(len(filtered)),'Includes subsequent approvals and reapprovals'),
    ])
    st.markdown('<div class="note"><b>Usage history, not voyage coverage.</b> This extraction contains approved plans only. Voyages with no approved WR plan and the coverage percentage require a complete voyage list.</div>',unsafe_allow_html=True)
    left,right=st.columns([1.3,1])
    with left:
        section('Approval activity','First recorded route approval versus subsequent approval events')
        months=pd.date_range(pd.Timestamp(start).replace(day=1),pd.Timestamp(end).replace(day=1),freq='MS')
        data=filtered.assign(Month=filtered['Approval timestamp (UTC)'].dt.tz_localize(None).dt.to_period('M').dt.to_timestamp())
        groups=['First recorded for route','Subsequent approval']
        counts=data.groupby(['Month','Approval category']).size().unstack(fill_value=0).reindex(index=months,columns=groups,fill_value=0).fillna(0)
        fig=go.Figure()
        for label,color in zip(groups,[TEAL,GOLD]):
            fig.add_bar(name=label,x=counts.index,y=counts[label],marker_color=color,hovertemplate='%{x|%b %Y}<br>%{y} events<extra>'+label+'</extra>')
        fig.update_layout(barmode='stack')
        fig.update_xaxes(tickformat='%b %y',dtick='M1')
        fig.update_yaxes(title='Approval events',rangemode='tozero')
        chart(fig,key='monthly_activity')
    with right:
        level=st.selectbox('Activity breakdown',['Fleet','Vessel'] if 'Fleet' in filtered else ['Vessel'],key='breakdown')
        if level=='Fleet':
            section('Activity by fleet','Approval events, not WR voyage-coverage percentages')
            top=filtered.groupby('Fleet').size().rename('Approval events').reset_index().sort_values('Approval events')
            top['Fleet label']='Fleet '+top['Fleet'].astype(str)
            ycol='Fleet label'
        else:
            section('Most active vessels','Approval activity, not a vessel performance ranking')
            top=vessel_summary(filtered).head(10).sort_values('Approval events')
            ycol='Vessel name'
        fig=px.bar(top,x='Approval events',y=ycol,orientation='h',text='Approval events',color_discrete_sequence=[TEAL])
        fig.update_traces(textposition='outside',cliponaxis=False)
        fig.update_yaxes(title=None)
        chart(fig,key='vessel_activity')
    section('Vessel activity register','All figures below follow the selected approval-date period and history filters.')
    summary=vessel_summary(filtered)
    table(summary,key='fleet_register')
    download(summary,'wr_vessel_activity.csv','fleet_export')
    if master is not None:
        with st.expander('Fleet master · including vessels without approval records'):
            roster=fleet_roster(master,filtered,full)
            if fleet_choice!='All fleets':roster=roster[roster['Fleet'].eq(fleet_choice)]
            st.caption('No records in this extraction does not prove that no WR plan exists or that a vessel failed to use WR. The voyage denominator is not available.')
            table(roster,key='fleet_roster')
            download(roster,'wr_fleet_master_status.csv','roster_export')
    with st.expander('What this first dashboard can measure'):
        st.write('Available: approval history, activity by vessel/month, repeated approvals, route-level plan estimates and plan-to-plan changes. Fleet summaries become available after uploading an IMO-to-fleet mapping.')
        st.write('Pending: voyages without approved WR, actual departure/arrival status, sailed route compliance, actual fuel savings and ETA accuracy. ETD/ETA and all fuel/CO₂/cost values in this extraction are planned estimates.')


def choose_route(filtered, prefix):
    vessels=sorted(filtered['Vessel name'].dropna().unique(),key=str.casefold)
    a,b=st.columns([1,2])
    vessel=a.selectbox('Vessel to inspect',vessels,key=prefix+'_vessel')
    cat=route_catalog(filtered[filtered['Vessel name'].eq(vessel)])
    keys=cat['_route_key'].tolist()
    labels={row['_route_key']:f'{row["Route name"]} · {date_text(row["Approval timestamp (UTC)"])} · {str(row["Route GUID"])[:8]}' for _,row in cat.iterrows()}
    key=b.selectbox('Route',keys,format_func=lambda k:labels[k],key=prefix+'_route')
    return key


def render_explorer(filtered, full):
    section('Route Explorer','Inspect every approval for a route, including events outside the sidebar date selection.')
    key=choose_route(filtered,'history')
    history=full.loc[full['_route_key'].eq(key)].sort_values('Approval timestamp (UTC)')
    first,last=history.iloc[0],history.iloc[-1]
    cards([('APPROVAL EVENTS',len(history),'Complete extracted history for this route'),
        ('UNIQUE PLANS',history['_plan_key'].nunique(),'Versions identified by Passage plan GUID'),
        ('FIRST APPROVAL',pd.Timestamp(first['Approval timestamp (UTC)']).strftime('%d/%m/%Y'),'First in extraction'),
        ('LATEST APPROVAL',pd.Timestamp(last['Approval timestamp (UTC)']).strftime('%d/%m/%Y'),'Latest in extraction')])
    st.markdown(f'**Route:** {escape(str(last["Route name"]))}  ·  **Voyage number:** {escape(str(last["Voyage number"]))}  ·  **IMO:** {last["IMO"]}')
    st.caption('Route GUID: '+str(last['Route GUID']))
    selected_metric=st.selectbox('Plan history metric',['Distance (NM)','Estimated fuel consumption (MT)','Average speed (kn)','Duration (days)','CO2 (MT)','Max wave height (m)','Total cost (USD)'],key='history_metric')
    fig=px.line(history,x='Approval timestamp (UTC)',y=selected_metric,markers=True,color_discrete_sequence=[TEAL],
        hover_data={'Passage plan GUID':True,'Approval sequence':True,'Approval timestamp (UTC)': '|%d/%m/%Y %H:%M'})
    fig.update_xaxes(title='Approval timestamp (UTC)',tickformat='%d/%m/%Y')
    chart(fig,300,'history_chart')
    st.caption('Values describe each plan’s own forecast horizon. A falling remaining-distance or fuel estimate is not proof of optimisation savings.')
    cols=['Approval sequence','Approval timestamp (UTC)','Unapproval timestamp (UTC)','Passage plan GUID','Reapproval event',
          'ETD (UTC)','ETA (UTC)','Distance (NM)','Estimated fuel consumption (MT)','CO2 (MT)','Total cost (USD)','Route deleted','Plan deleted']
    table(history[cols],key='history_table')
    download(public(history),'wr_route_history.csv','history_export')
    with st.expander('Departure / destination map and coordinates'):
        st.caption('Endpoint markers for the latest approved plan. The extraction contains no route waypoints, so these markers do not represent the full route or sailed track.')
        endpoints=pd.DataFrame({'Location':['Departure','Destination'],
            'Latitude':[last['Departure latitude'],last['Destination latitude']],
            'Longitude':[last['Departure longitude'],last['Destination longitude']]})
        valid=endpoints[endpoints['Latitude'].between(-90,90)&endpoints['Longitude'].between(-180,180)]
        if not valid.empty:
            st.map(valid,latitude='Latitude',longitude='Longitude',use_container_width=True)
        table(endpoints)
        st.write('Departure: '+str(last['Departure']))
        st.write('Destination: '+str(last['Destination']))


def render_comparison(filtered,full):
    section('Plan Comparison','Compare approved estimates for the same route. No actual savings are inferred.')
    key=choose_route(filtered,'compare')
    history=full.loc[full['_route_key'].eq(key)].sort_values('Approval timestamp (UTC)').reset_index(drop=True)
    if len(history)<2:
        st.info('This route has one approval event in the extraction. Select another route to compare revisions.')
        return
    options=list(range(len(history)))
    label=lambda i:f'#{history.iloc[i]["Approval sequence"]} · {date_text(history.iloc[i]["Approval timestamp (UTC)"])} · {str(history.iloc[i]["Passage plan GUID"])[:8]}'
    a,b=st.columns(2)
    before=a.selectbox('Reference approval',options,index=0,format_func=label,key='reference_plan')
    after=b.selectbox('Compared approval',options,index=len(history)-1,format_func=label,key='compared_plan')
    old,new=history.iloc[before],history.iloc[after]
    if before==after:st.info('Both selectors currently refer to the same approval event.')
    st.markdown('<div class="note">Later plans may start from a new vessel position and cover a shorter remaining passage. Differences below describe plan estimates; they do not quantify achieved fuel or CO₂ savings.</div>',unsafe_allow_html=True)
    cards([('REFERENCE ETD',date_text(old['ETD (UTC)']),'UTC'),('COMPARED ETD',date_text(new['ETD (UTC)']),'UTC'),
           ('REFERENCE ETA',date_text(old['ETA (UTC)']),'UTC'),('COMPARED ETA',date_text(new['ETA (UTC)']),'UTC')])
    metrics=['Distance (NM)','Duration (days)','Average speed (kn)','Estimated fuel consumption (MT)','CO2 (MT)','Max wave height (m)','Total cost (USD)','CII (gCO2/NM.MT)']
    rows=[]
    for metric in metrics:
        x,y=old[metric],new[metric]
        delta=y-x if pd.notna(x) and pd.notna(y) else float('nan')
        rows.append({'Metric':metric,'Reference':x,'Compared':y,'Difference':delta,'Difference (%)':delta/x*100 if pd.notna(x) and x!=0 else float('nan')})
    changes=pd.DataFrame(rows)
    a,b=st.columns([1.25,1])
    with a:
        section('Estimated plan differences','Compared approval minus reference approval')
        table(changes,key='comparison_table')
    with b:
        metric=st.selectbox('Visualise one metric',metrics,key='comparison_metric')
        fig=go.Figure(go.Bar(x=['Reference','Compared'],y=[old[metric],new[metric]],marker_color=[NAVY,TEAL],text=[number(old[metric],2),number(new[metric],2)],textposition='outside'))
        fig.update_yaxes(title=metric)
        chart(fig,320,'comparison_chart')
    eta_hours=(new['ETA (UTC)']-old['ETA (UTC)']).total_seconds()/3600 if pd.notna(new['ETA (UTC)']) and pd.notna(old['ETA (UTC)']) else None
    if eta_hours is not None:st.caption(f'Planned ETA change: {eta_hours:+.1f} hours. Actual arrival is not included in this extraction.')
    download(changes,'wr_plan_comparison.csv','comparison_export')


def render_quality(filtered, full, audit):
    section('Data Quality','Review source values without silently correcting or deleting historical records.')
    rules=quality_summary(filtered)
    flagged=filtered[list(QUALITY_RULES)].fillna(False).any(axis=1)
    cards([('RECORDS TO REVIEW',int(flagged.sum()),'Records with one or more checks'),
        ('REAPPROVAL EVENTS',int(filtered['Reapproval event'].sum()),'Retained as approval history'),
        ('DELETION FLAGS',int(filtered['_deleted'].sum()),'Route or plan marked deleted'),
        ('WRAPPED CSV RECORDS',audit['wrapped_records'],'Decoded safely during import · whole file')])
    a,b=st.columns([1.15,1])
    with a:
        section('Validation checks','Counts apply to the current selection; checks may overlap.')
        table(rules,key='quality_checks')
    with b:
        section('Source completeness','Original extraction fields · selected records')
        completeness=pd.DataFrame({'Field':REQUIRED_COLUMNS,'Missing':[int(filtered[c].isna().sum()) for c in REQUIRED_COLUMNS]})
        table(completeness.sort_values('Missing',ascending=False),key='completeness',height=400)
    choices=['Any review flag',*QUALITY_RULES.values()]
    choice=st.selectbox('Inspect flagged records',choices,key='review_filter')
    mask=flagged if choice==choices[0] else filtered[next(k for k,v in QUALITY_RULES.items() if v==choice)].fillna(False)
    review=filtered.loc[mask].copy()
    review['Review notes']=review.apply(lambda row:'; '.join(label for key,label in QUALITY_RULES.items() if bool(row[key])),axis=1)
    cols=['Vessel name','IMO','Route name','Approval timestamp (UTC)','Review notes','Duration (s)','Total cost (USD)','ETD (UTC)','ETA (UTC)','Passage plan GUID']
    table(review[cols],key='review_records')
    download(public(review),'wr_records_to_review.csv','review_export')
    with st.expander('Definitions and pending source clarification'):
        st.write('A row is an approval event. Passage plan GUID identifies a plan; Route GUID identifies a routing object. The voyage number is not assumed to be a unique port-to-port leg. Previously deleted or unapproved plans still represent historical approvals.')
        st.write('NULL unapproval timestamps mean only “no unapproval recorded”, not proof that a plan remains active. ETA and ETD are estimates, so this dashboard does not label routes as actually completed or ongoing.')
        st.write('Cost values above USD 10 million are flagged for review, not automatically classified as errors. Inconsistent durations and approvals after planned arrival also need source clarification.')
        st.write('Pending additional data: all voyage legs including those without approved plans, actual departure/arrival, actual voyage status, a reliable voyage-to-route link and any WR exclusions. These are needed before calculating WR voyage coverage.')
        st.caption(f'Entire extraction: {len(full):,} approval events; {full["_plan_key"].nunique():,} unique plans; {full["_route_key"].nunique():,} route IDs; {full["IMO"].nunique()} vessels.')


def main():
    with st.sidebar:
        st.markdown('### TECHNOMAR')
        st.caption('PERFORMANCE DEPARTMENT')
        st.divider()
        st.markdown('**Historical extraction**')
        uploaded=st.file_uploader('Replace extraction for this session',type=['csv'],key='extraction_upload')
    try:
        payload=uploaded.getvalue() if uploaded else SNAPSHOT.read_bytes()
        filename=uploaded.name if uploaded else SNAPSHOT.name
        full,audit=load_data(payload,filename)
    except (ValueError,UnicodeError,FileNotFoundError) as exc:
        st.error(str(exc))
        return
    if full['Approval timestamp (UTC)'].notna().sum()==0:
        st.error('No valid approval timestamps are available in this extraction.')
        return
    with st.sidebar:
        st.caption(f'{len(full):,} approval records · {full["IMO"].nunique()} vessels')
        fleet_file=st.file_uploader('Replace fleet mapping · CSV',type=['csv'],help='Columns: ShipName, IMONo (or IMO), Fleet. Comma and semicolon separators supported.',key='fleet_mapping')
        master=None
        try:
            fleet_payload=fleet_file.getvalue() if fleet_file else (APP_DIR/'Fleet.csv').read_bytes()
            master=parse_fleet_master(fleet_payload)
            full=attach_fleets(full,master)
            st.caption(f'{len(master)} vessels in fleet master · {master["Fleet"].nunique()} fleets')
            missing_imos=int(master['IMO'].eq('').sum())
            if missing_imos:st.caption(f'{missing_imos} master entry has no IMO; exact name matching is flagged in the register.')
        except (FileNotFoundError,ValueError,pd.errors.ParserError,UnicodeError) as exc:
            st.warning('Fleet categorisation unavailable: '+str(exc))
        st.divider()
        st.markdown('**Explore the history**')
        fleet_choice='All fleets'
        if 'Fleet' in full:
            fleet_choice=st.selectbox('Fleet',['All fleets',*sorted(full['Fleet'].unique(),key=lambda v:(not str(v).isdigit(),int(v) if str(v).isdigit() else str(v)))],key='fleet_choice')
        eligible=full if fleet_choice=='All fleets' else full[full['Fleet'].eq(fleet_choice)]
        vessel_choices=sorted(eligible['Vessel name'].dropna().unique(),key=str.casefold)
        chosen=st.multiselect('Vessels',vessel_choices,key='vessel_filter',placeholder='All vessels')
        minimum=full['Approval timestamp (UTC)'].min().date()
        maximum=full['Approval timestamp (UTC)'].max().date()
        preset=st.selectbox('Approval period',['All extracted history','Current month','Previous month','YTD','Custom range'],key='period_preset')
        anchor=audit['extraction_date']
        if preset=='Current month':start,end=anchor.replace(day=1),anchor
        elif preset=='Previous month':
            end=anchor.replace(day=1)-timedelta(days=1);start=end.replace(day=1)
        elif preset=='YTD':start,end=date(anchor.year,1,1),anchor
        else:start,end=minimum,maximum
        if preset=='Custom range':
            dates=st.date_input('Approval dates (UTC)',(start,end),format='DD/MM/YYYY',key='custom_dates')
            if len(dates)!=2:st.info('Choose both dates.');return
            start,end=dates
        st.caption(f'{start:%d/%m/%Y} – {end:%d/%m/%Y} UTC')
        history_scope=st.selectbox('History scope',['All historical approvals','Without deletion flags','With deletion flags'],key='history_scope')
        unapproval_scope=st.selectbox('Unapproval record',['All records','Unapproval recorded','No unapproval recorded'],key='unapproval_scope')
        st.divider()
        st.caption('Coverage denominator pending')
        st.caption('Voyages without an approved WR plan cannot be identified from this file alone.')
    filtered=eligible.copy()
    if chosen:filtered=filtered[filtered['Vessel name'].isin(chosen)]
    times=filtered['Approval timestamp (UTC)']
    filtered=filtered[times.ge(pd.Timestamp(start,tz='UTC')) & times.lt(pd.Timestamp(end+timedelta(days=1),tz='UTC'))]
    if history_scope=='Without deletion flags':filtered=filtered[~filtered['_deleted']]
    elif history_scope=='With deletion flags':filtered=filtered[filtered['_deleted']]
    if unapproval_scope!='All records':filtered=filtered[filtered['Unapproval record'].eq(unapproval_scope)]
    st.markdown(f'<div class="hero"><span class="tag">HISTORICAL REVIEW · CSV SNAPSHOT</span><div class="eyebrow">TECHNOMAR / PERFORMANCE INTELLIGENCE</div><h1>Weather Routing</h1><p>Explore approved plans. Trace revisions. Understand routing activity.</p></div>',unsafe_allow_html=True)
    st.caption(f'Extract dated {audit["extraction_date"]:%d/%m/%Y} · latest approval {date_text(audit["last_approval"])} UTC · {len(filtered):,} records in selection')
    view=st.radio('Dashboard view',['Fleet Overview','Route Explorer','Plan Comparison','Data Quality','API Connection'],horizontal=True,label_visibility='collapsed',key='dashboard_view')
    if view=='API Connection':
        from connection_view import render_connection
        render_connection()
        return
    if filtered.empty:
        st.info('No approval records match these filters. Widen the period or change the vessel/history selection.')
        return
    if view=='Fleet Overview':render_overview(filtered,full,start,end,master,fleet_choice)
    elif view=='Route Explorer':render_explorer(filtered,full)
    elif view=='Plan Comparison':render_comparison(filtered,full)
    elif view=='Data Quality':render_quality(filtered,full,audit)
    st.caption('Source: GTT Marine approved Weather Routing extraction. Planned estimates are not actual voyage results. This dashboard makes no automatic API requests.')


if __name__=='__main__':
    main()
