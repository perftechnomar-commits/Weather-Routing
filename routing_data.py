"""Historical Weather Routing extraction. No network calls or credentials."""
from __future__ import annotations
import csv
import io
import re
from datetime import date
import pandas as pd

DATE_COLUMNS = ['Approval timestamp (UTC)', 'Unapproval timestamp (UTC)', 'ETD (UTC)', 'ETA (UTC)']
NUMERIC_COLUMNS = ['Departure latitude', 'Departure longitude', 'Destination latitude', 'Destination longitude',
    'Distance (NM)', 'Duration (s)', 'Average speed (kn)', 'Estimated fuel consumption (MT)', 'CO2 (MT)',
    'Total cost (USD)', 'CII (gCO2/NM.MT)', 'Max wave height (m)']
REQUIRED_COLUMNS = ['Vessel name', 'IMO', 'Route GUID', 'Voyage number', 'Route name', 'Passage plan GUID',
    *DATE_COLUMNS, 'Departure', 'Destination', *NUMERIC_COLUMNS, 'Route deleted', 'Plan deleted']


def parse_extraction(payload: bytes, filename: str = '') -> tuple[pd.DataFrame, dict]:
    text = payload.decode('utf-8-sig')
    reader = csv.reader(io.StringIO(text, newline=''))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        raise ValueError('The extraction is empty.')
    if len(set(header)) != len(header):
        raise ValueError('The CSV has duplicate column names.')
    missing = sorted(set(REQUIRED_COLUMNS) - set(header))
    if missing:
        raise ValueError('Missing extraction columns: ' + ', '.join(missing))
    records, wrapped, malformed = [], 0, []
    for record_no, row in enumerate(reader, start=2):
        if not row or all(not value.strip() for value in row):
            continue
        if len(row) == 1:
            row = next(csv.reader([row[0]]))
            wrapped += 1
        if len(row) != len(header):
            malformed.append(record_no)
        else:
            records.append(row)
    if malformed:
        raise ValueError(f'{len(malformed)} CSV records have an unexpected column count (first records: {malformed[:5]}). No records were silently dropped.')
    if not records:
        raise ValueError('No approval records were found.')
    df = pd.DataFrame(records, columns=header)
    for col in df:
        df[col] = df[col].str.strip().replace({'NULL': pd.NA, 'null': pd.NA, '': pd.NA})
    raw_dates = {col: df[col].copy() for col in DATE_COLUMNS}
    invalid_numeric = pd.Series(False, index=df.index)
    for col in NUMERIC_COLUMNS:
        raw = df[col]
        df[col] = pd.to_numeric(raw, errors='coerce')
        invalid_numeric |= raw.notna() & df[col].isna()
    for col in DATE_COLUMNS:
        df[col] = pd.to_datetime(df[col], errors='coerce', utc=True, format='mixed')
    invalid_date = pd.Series(False, index=df.index)
    for col in DATE_COLUMNS:
        invalid_date |= raw_dates[col].notna() & df[col].isna()
    for col in ['Route deleted', 'Plan deleted']:
        df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')
    # GUID and approval timestamp together identify an approval event, not a unique plan.
    df['_event_duplicate'] = df.duplicated(['IMO', 'Passage plan GUID', 'Approval timestamp (UTC)'], keep=False)
    df['_route_key'] = df['IMO'].fillna('Unknown IMO') + ':' + df['Route GUID'].fillna('Unknown route')
    df['_plan_key'] = df['IMO'].fillna('Unknown IMO') + ':' + df['Passage plan GUID'].fillna('Unknown plan')
    df['_invalid_date'] = invalid_date
    df['_invalid_numeric'] = invalid_numeric
    df['_missing_identity'] = df[['IMO', 'Route GUID', 'Passage plan GUID', 'Vessel name']].isna().any(axis=1)
    df['_negative_duration'] = df['Duration (s)'].lt(0)
    df['_approval_after_eta'] = df['Approval timestamp (UTC)'].gt(df['ETA (UTC)'])
    df['_eta_before_etd'] = df['ETA (UTC)'].lt(df['ETD (UTC)'])
    elapsed = (df['ETA (UTC)'] - df['ETD (UTC)']).dt.total_seconds()
    df['_duration_mismatch'] = elapsed.sub(df['Duration (s)']).abs().gt(60)
    df['_high_cost'] = df['Total cost (USD)'].gt(10_000_000)
    df['_unapproval_before'] = df['Unapproval timestamp (UTC)'].lt(df['Approval timestamp (UTC)'])
    df['_missing_summary'] = df[['Distance (NM)', 'ETA (UTC)', 'Estimated fuel consumption (MT)', 'Average speed (kn)']].isna().any(axis=1)
    df['_missing_approval'] = df['Approval timestamp (UTC)'].isna()
    df['_deleted'] = df['Route deleted'].eq(1) | df['Plan deleted'].eq(1)
    df['Duration (days)'] = df['Duration (s)'] / 86400
    df['Approval relative to ETD'] = 'At / after planned departure'
    df.loc[df['Approval timestamp (UTC)'].lt(df['ETD (UTC)']), 'Approval relative to ETD'] = 'Before planned departure'
    df.loc[df['Approval timestamp (UTC)'].isna() | df['ETD (UTC)'].isna(), 'Approval relative to ETD'] = 'Unknown'
    df['Unapproval record'] = df['Unapproval timestamp (UTC)'].notna().map({True:'Unapproval recorded', False:'No unapproval recorded'})
    df = df.sort_values('Approval timestamp (UTC)', kind='stable', na_position='last').reset_index(drop=True)
    df['Approval sequence'] = df.groupby('_route_key', sort=False).cumcount() + 1
    df['Approval category'] = df['Approval sequence'].eq(1).map({True:'First recorded for route',False:'Subsequent approval'})
    first = df.groupby('_plan_key', sort=False)['Approval timestamp (UTC)'].transform('min')
    df['Reapproval event'] = df['Approval timestamp (UTC)'].gt(first)
    match = re.search(r'(20\d{6})', filename)
    try:
        extracted = date.fromisoformat(f'{match[1][:4]}-{match[1][4:6]}-{match[1][6:8]}') if match else df['Approval timestamp (UTC)'].max().date()
    except (ValueError, AttributeError):
        extracted = date.today()
    return df, dict(rows=len(df), wrapped_records=wrapped, filename=filename, extraction_date=extracted,
                    first_approval=df['Approval timestamp (UTC)'].min(), last_approval=df['Approval timestamp (UTC)'].max())


QUALITY_RULES = {
    '_negative_duration': 'Negative duration',
    '_duration_mismatch': 'Duration differs from ETA − ETD by >60 seconds',
    '_approval_after_eta': 'Approval timestamp after planned ETA',
    '_high_cost': 'Cost above USD 10 million (review threshold)',
    '_eta_before_etd': 'ETA earlier than ETD',
    '_unapproval_before': 'Unapproval earlier than approval',
    '_missing_summary': 'Missing key summary value',
    '_missing_identity': 'Missing vessel / route / plan identifier',
    '_missing_approval': 'Missing approval timestamp',
    '_invalid_date': 'Unparseable date value',
    '_invalid_numeric': 'Unparseable numeric value',
    '_event_duplicate': 'Repeated approval-event key',
}


def quality_summary(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{'Check': label, 'Records': int(df[key].fillna(False).sum())} for key,label in QUALITY_RULES.items()])


def route_catalog(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    latest = df.sort_values('Approval timestamp (UTC)', kind='stable').drop_duplicates('_route_key', keep='last').copy()
    grouped = df.groupby('_route_key', sort=False)
    latest['Approval events'] = latest['_route_key'].map(grouped.size())
    latest['Unique plans'] = latest['_route_key'].map(grouped['_plan_key'].nunique())
    latest['First approval in selection'] = latest['_route_key'].map(grouped['Approval timestamp (UTC)'].min())
    return latest.sort_values('Approval timestamp (UTC)', ascending=False)


def safe_csv(df: pd.DataFrame) -> bytes:
    export = df.copy()
    for col in export:
        if isinstance(export[col].dtype, pd.DatetimeTZDtype):
            export[col] = export[col].dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        elif not pd.api.types.is_numeric_dtype(export[col]) and not pd.api.types.is_bool_dtype(export[col]):
            export[col] = export[col].map(lambda v: "'" + v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v)
    return export.to_csv(index=False).encode('utf-8-sig')


def parse_fleet_master(payload: bytes) -> pd.DataFrame:
    master = pd.read_csv(io.BytesIO(payload),sep=None,engine='python',dtype=str,encoding='utf-8-sig').fillna('')
    master.columns = master.columns.str.strip()
    master = master.rename(columns={'IMONo':'IMO'})
    if not {'IMO','Fleet'}.issubset(master):
        raise ValueError('Fleet mapping needs IMO (or IMONo) and Fleet columns.')
    if 'ShipName' not in master: master['ShipName']=''
    for col in ['IMO','Fleet','ShipName']: master[col]=master[col].str.strip()
    master['IMO']=master['IMO'].str.replace(r'\.0$','',regex=True)
    master['Fleet']=master['Fleet'].str.replace(r'\.0$','',regex=True).replace('', 'Unassigned')
    if master.loc[master['IMO'].ne(''),'IMO'].duplicated().any():
        raise ValueError('Fleet master has repeated IMOs. Keep one authoritative entry per IMO.')
    master['_name_key']=master['ShipName'].str.casefold().str.replace(r'[^a-z0-9]+','',regex=True)
    if master.loc[master['IMO'].eq(''),'_name_key'].duplicated().any():
        raise ValueError('Fleet master has ambiguous vessel names without IMOs.')
    master['_master_key']=master.apply(lambda r:'IMO:'+r['IMO'] if r['IMO'] else 'NAME:'+r['_name_key'],axis=1)
    return master


def attach_fleets(df: pd.DataFrame,master: pd.DataFrame) -> pd.DataFrame:
    out=df.copy()
    known=master.loc[master['IMO'].ne('')].set_index('IMO')
    out['Fleet']=out['IMO'].map(known['Fleet'])
    out['_master_key']=out['IMO'].map(known['_master_key'])
    out['_mapping_method']=out['Fleet'].notna().map({True:'IMO match',False:'Unmapped'})
    # Exact normalised name fallback only where the master has no IMO, never override a conflicting IMO.
    missing=master.loc[master['IMO'].eq('') & master['_name_key'].ne('')].set_index('_name_key')
    names=out['Vessel name'].str.casefold().str.replace(r'[^a-z0-9]+','',regex=True)
    fallback=out['Fleet'].isna() & names.isin(missing.index)
    out.loc[fallback,'Fleet']=names[fallback].map(missing['Fleet'])
    out.loc[fallback,'_master_key']=names[fallback].map(missing['_master_key'])
    out.loc[fallback,'_mapping_method']='Name match · master IMO missing'
    out['Fleet']=out['Fleet'].fillna('Unmapped')
    return out


def fleet_roster(master: pd.DataFrame, selection: pd.DataFrame, full: pd.DataFrame) -> pd.DataFrame:
    roster=master[['ShipName','IMO','Fleet','_master_key']].copy()
    counts=selection.groupby('_master_key').size()
    roster['Approval events']=roster['_master_key'].map(counts).fillna(0).astype(int)
    roster['Unique plans']=roster['_master_key'].map(selection.groupby('_master_key')['_plan_key'].nunique()).fillna(0).astype(int)
    roster['Latest selected approval']=roster['_master_key'].map(selection.groupby('_master_key')['Approval timestamp (UTC)'].max())
    present=set(full['_master_key'].dropna())
    roster['Extraction status']=roster['_master_key'].map(lambda k:'Records in selection' if counts.get(k,0)>0 else ('No records for selected filters' if k in present else 'No records in this extraction'))
    roster['Identity note']=roster['IMO'].eq('').map({True:'IMO missing in master · exact name match only',False:''})
    return roster.drop(columns='_master_key')
