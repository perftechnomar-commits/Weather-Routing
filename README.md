# Weather Routing · historical dashboard

This initial dashboard uses the GTT Marine historical extraction dated 16 November 2026. It opens immediately with the included data; no API credentials are needed to review the dashboard.

## Quick visual review
Open `Weather_Routing_Preview.html` in a desktop browser. This self-contained offline preview embeds the actual extraction, the fleet mapping and chart library. It supports fleet/vessel/date/history filters and four views: Fleet Overview, Route Explorer, Plan Comparison and Data Quality. It makes no API requests. If your download viewer displays source code, save the HTML and open it in Chrome or Edge.

## Python engine with HTML presentation
The default **Interactive Dashboard** workspace renders the reviewed HTML design directly inside Streamlit. Python in `routing_data.py` imports, validates and prepares the extraction, fleet mapping and approval history. `preview_renderer.py` injects that current Python-prepared data into the HTML view. The browser handles instantaneous display filtering and chart interactions. This is a running Streamlit app, not a redirect to a downloaded HTML file.

**Data & API Tools** preserves the native detailed analysis, endpoint maps and API connection test. Source-file replacement is available in Streamlit's collapsible sidebar. Uploads update the HTML dashboard using the current session's data. Selections within the HTML view are local to that view and are independent of the native tools.

Deploy every file in the ZIP, including `preview_renderer.py`, the HTML template and `.streamlit/config.toml`. The light theme applies to the native tools; the HTML interface uses its own consistent colours.

## Run the complete Streamlit dashboard
1. Keep all files in the extracted folder together, including both CSVs.
2. Install dependencies: `python -m pip install -r requirements.txt`.
3. Start: `python -m streamlit run app.py`.

For an existing Streamlit Cloud repository, replace/add the files from this folder, including the updated `requirements.txt`, `routing_data.py`, `connection_view.py`, `Fleet.csv` and the historical extraction. Keep `app.py` as the entry point. No historical API call or refresh is needed for this CSV build.

## Views
- **Fleet Overview:** counts of approval events, unique plans and route IDs, monthly activity, fleet/vessel activity breakdown and the full fleet roster including vessels without extracted records.
- **Route Explorer:** chronological approval history, plan estimate trends, endpoint map and export. The chosen route shows its entire extracted history, even when some events fall outside the sidebar filters.
- **Plan Comparison:** compare any two approval events within a route, with numeric changes and planned ETA shift. Differences are not presented as achieved savings.
- **Data Quality:** explicit flags for inconsistent or missing values, deleted history, reapprovals and source completeness.
- **API Connection:** the original latest-approved-plan authentication/retrieval test remains available. It does not yet feed the historical dashboard. No network call is made until the user runs a test.

## Fleet mapping
`Fleet.csv` is the default authoritative categorisation. Comma and semicolon delimiters are supported. Vessels are joined by IMO, not by display name. The master contains 80 vessels in 10 fleets. 54 of the 55 extracted vessels match by IMO; Istanbul Express has a blank IMO in the master, so a flagged exact normalised name fallback is used. GSL Myny and MYNY have different IMOs and remain separate vessels. 25 fleet-master vessels have no records in this extraction; that does not establish that they had voyages without WR.

An uploaded replacement extraction or fleet mapping applies to the current browser session. To change the deployed default data for all users, replace the corresponding bundled CSV. Fleet filters use the supplied master; no vessel is assigned a guessed fleet.

## Counting rules
- One CSV row is one approval event. Source totals: 1,028 events, 1,009 unique Passage plan GUIDs, 906 Route GUIDs and 55 vessel IMOs.
- Fifteen plans have repeated approvals, representing 19 additional approval events. These are retained. The current source has no duplicate plan-plus-approval-timestamp event keys.
- Route IDs are routing objects; they are not asserted to equal actual voyage or port-to-port-leg counts. Voyage numbers may cover multiple routes.
- Sidebar dates filter **approval timestamps in UTC**. Calendar shortcuts are anchored to the extraction date, not the live clock.
- All historical approvals are included by default, including subsequently unapproved or deleted plans. Optional history filters make those exclusions explicit.
- First/subsequent approval labels are assigned against the full extraction, before date filtering. “First” means first recorded in this extraction.
- No unapproval timestamp means only no unapproval recorded; it is not proof that a plan is currently active.

## Meaning and limits
All distance, fuel, CO2, cost, CII, speed, duration and weather values are plan estimates. Revised plans can have different start positions and forecast horizons, so differences are not actual savings. Fuel/CO2/cost are never summed across overlapping plan revisions as fleet savings. ETD/ETA do not establish actual voyage completion. Maps show departure/destination markers only, not a route track.

Voyages without an approved WR plan and the WR coverage percentage remain unavailable until a complete voyage/leg denominator and reliable route link are supplied. Actual fuel savings, arrival accuracy and sailed route compliance additionally require actual voyage results and appropriate baselines.

## Import and review checks
The extraction contains 167 whole-row quoted records. The importer decodes those records without dropping them and rejects unexpected row widths. Review flags are visible rather than silently changing values: one negative duration, 11 duration mismatches above 60 seconds, 15 approvals after planned ETA and six costs above an explicit USD 10 million review threshold. High costs are flagged for review, not automatically declared wrong. Missing key summaries affect one record.

CSV exports include the selected data and protect formula-like text. Preserve GUIDs and approval timestamps for future incremental imports. API automation and persistent incremental ingestion are not implemented in this initial CSV review version.

## Existing API diagnostics
See `API_DIAGNOSTICS.md` for the preserved connection-test request contract and usage.
