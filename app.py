"""Public synthetic demo. Uploaded workbooks stay in the current session's memory."""
from io import BytesIO
from decimal import Decimal
import altair as alt
import pandas as pd
import streamlit as st
from scripts.audit import all_passed, audit_batch, display_frame
from scripts.decompte_extractor import extract_decompte
from scripts.policy import load_policy
from scripts.reports import REPORT_NAMES, verified_report
from scripts.workbooks import MAX_FILES, preview_workbook, workbook_bytes

st.set_page_config(page_title='Construction Project Monitoring', page_icon='🏗️', layout='wide')
st.sidebar.title('🏗️ Infrastructure Analytics Demo')
st.sidebar.caption('Construction Monitoring System')
page = st.sidebar.radio('Go to', ['Overview', 'Financial Audit', 'Technical Monitoring', 'Document Analysis', 'Report Center'])
st.sidebar.info('Synthetic demonstration. Uploads do not update the saved demo reports.')
st.title('🏗️ Infrastructure Analytics Demo | Project Monitoring')
st.info('DEMO VERSION — All bundled data are synthetic. Use synthetic documents only in this public demo.')

try:
    policy = load_policy()
except (ValueError, KeyError, OSError) as error:
    st.error(f'Invalid project configuration: {error}')
    st.stop()

with st.expander('Financial assumptions used in this demo'):
    st.write(policy.name)
    st.write(f'Retention: {policy.retention_rate:.0%}; VAT: {policy.vat_rate:.0%}; '
             f'VAT base: {policy.vat_base.replace("_", " ")}; tolerance: {policy.tolerance} DH; '
             f'rounding: half up to two decimal places. Rule version: {policy.version}.')
    st.caption('These assumptions are not evidence of contractual entitlement or tax compliance. '
               'Negative corrections are unsupported. Blank opening balance is zero only for an identified first statement.')


@st.cache_data(show_spinner=False)
def read_table(data, sheet):
    return pd.read_excel(BytesIO(data), sheet_name=sheet)


def report_table(filename, columns, sheet='Sheet1'):
    data, manifest = verified_report(filename)
    frame = read_table(data, sheet)
    if frame.empty or not set(columns).issubset(frame.columns):
        raise ValueError('Report is empty or its required columns are missing.')
    st.caption(f"Saved synthetic demo report • Generated {manifest['generated_at_utc']} • {manifest['rule_version']}")
    return frame


def show_status(statuses, success_message):
    values = list(statuses)
    if all_passed(values):
        st.success(success_message)
    else:
        count = sum(value != 'OK' for value in values)
        st.warning(f'{count} record(s) require review or have missing/unknown status. No overall pass is confirmed.')


def saved_page():
    if page == 'Overview':
        st.subheader('Financial Overview')
        frame = report_table('financial_analysis.xlsx', ['Decompte', 'Cumul actuel HT', 'Travaux du mois HT'])
        frame['Number'] = pd.to_numeric(frame['Decompte'].astype(str).str.extract(r'^D(\d+)$')[0], errors='raise')
        if frame['Number'].isna().any() or frame['Number'].duplicated().any():
            raise ValueError('Invalid or duplicate statement numbers in overview report.')
        frame = frame.sort_values('Number')
        cumulative = Decimal(str(frame['Cumul actuel HT'].iloc[-1]))
        ratio = cumulative * (Decimal('1') + policy.vat_rate) / policy.contract_ttc
        a, b, c = st.columns(3)
        a.metric('Cumulative Works (DH HT)', f'{cumulative:,.2f}')
        b.metric('Demo Contract Value (DH TTC)', f'{policy.contract_ttc:,.2f}')
        c.metric('Indicative Contract Valuation', f'{ratio:.2%}')
        st.caption('Indicative gross works valuation before retention, using the configured VAT rate. '
                   'This is not physical progress or a certified payment amount.')
        for title, column, chart_type in [('Cumulative Financial Evolution', 'Cumul actuel HT', 'line'),
                                          ('Works Recorded per Decompte', 'Travaux du mois HT', 'bar')]:
            st.subheader(title)
            chart = alt.Chart(frame).mark_line(point=True) if chart_type == 'line' else alt.Chart(frame).mark_bar()
            st.altair_chart(chart.encode(x=alt.X('Decompte:N', sort=frame['Decompte'].tolist()),
                                         y=alt.Y(f'{column}:Q', axis=alt.Axis(format=',.0f')),
                                         tooltip=['Decompte', alt.Tooltip(f'{column}:Q', format=',.2f')]), width='stretch')
        st.dataframe(frame.drop(columns='Number'), hide_index=True, width='stretch')
    elif page == 'Financial Audit':
        st.header('🔍 Financial Audit')
        st.caption('These are saved demo results, independent of your uploaded analysis.')
        continuity = report_table('financial_audit.xlsx', ['Comparison', 'Difference DH', 'Status'])
        st.subheader('Cumulative Continuity Checks')
        st.dataframe(continuity, hide_index=True, width='stretch')
        show_status(continuity['Status'], 'All saved demo continuity checks passed.')
        taxes = report_table('verification_retention_tva.xlsx', ['Décompte', 'Statut'])
        st.subheader('Retention, VAT and TTC Verification')
        st.dataframe(taxes, hide_index=True, width='stretch')
        show_status(taxes['Statut'], 'All saved demo arithmetic checks passed under the displayed assumptions.')
    elif page == 'Technical Monitoring':
        st.header('🏗️ Technical Monitoring')
        technical = report_table('audit_technique_valide.xlsx', ['Categorie', 'Statut validation', 'Review reason'], 'Controle_D3_D4')
        a, b, c = st.columns(3)
        a.metric('Work Items Examined', len(technical))
        b.metric('Passed Checks', int((technical['Statut validation'] == 'OK').sum()))
        c.metric('Records Requiring Review', int((technical['Statut validation'] != 'OK').sum()))
        categories = technical['Categorie'].dropna().unique().tolist()
        selected = st.selectbox('Select Construction Category', categories)
        filtered = technical[technical['Categorie'] == selected]
        st.dataframe(filtered, hide_index=True, width='stretch')
        st.bar_chart(filtered['Statut validation'].fillna('MISSING DATA').value_counts())
        st.caption('Quantity arithmetic and contract-quantity screening only. Manual demo flags are explicitly explained; '
                   'they do not prove construction errors or validate D3 source measurements.')
    elif page == 'Report Center':
        st.header('📥 Report Download Center')
        st.write('Download traceable, saved synthetic demo reports. Uploaded documents do not refresh these files.')
        for label, filename in REPORT_NAMES.items():
            try:
                data, manifest = verified_report(filename)
                st.download_button(label=f'Download {label}', data=data, file_name=filename,
                                   mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key=filename)
            except ValueError as error:
                st.warning(f'{label}: {error}')


if page != 'Document Analysis':
    try:
        saved_page()
    except (ValueError, KeyError, OSError, IndexError) as error:
        st.error(f'Demo report unavailable: {error}')
        st.info('To rebuild saved demo reports locally: python -m scripts.reports. Document Analysis remains available.')
else:
    st.header('📤 Excel Document Import')
    st.caption('Session-only analysis. Files are not written to disk or added to saved demo reports. '
               'Limits: 10 MiB per file, 50 MiB expanded, 20 sheets, 10,000 rows and 200 columns.')
    st.caption('Formula cells use saved cached results; recalculate and save the workbook before upload. Cache freshness cannot be certified here.')
    uploaded = st.file_uploader('Choose a synthetic Excel document', type=['xlsx'], key='decompte_upload')
    if uploaded is not None:
        try:
            data = workbook_bytes(uploaded)
            names, _ = preview_workbook(data)
            selected_sheet = st.selectbox('Select Worksheet for Preview and Analysis', names)
            _, rows = preview_workbook(data, selected_sheet)
            preview = pd.DataFrame(rows).dropna(how='all').dropna(axis=1, how='all')
            st.subheader('Worksheet Preview — first 30 rows')
            st.dataframe(preview.fillna('').astype(str), hide_index=True, width='stretch')
            result = extract_decompte(data, sheet_name=selected_sheet, policy=policy)
            st.subheader('Automatic Financial Verification')
            a, b, c = st.columns(3)
            a.metric('Executed Works (DH HT)', f"{result['Works HT']:,.2f}")
            b.metric('Retention (DH)', f"{result['Retention']:,.2f}")
            c.metric('Total TTC (DH)', f"{result['TTC']:,.2f}")
            if result['Status'] == 'OK':
                st.success('Statement arithmetic and cumulative identity passed under the displayed assumptions.')
            else:
                st.warning(f"{result['Status']}: {result['Validation issues']}")
            st.dataframe(display_frame([result]), hide_index=True, width='stretch')
            st.caption('Single-statement checks do not certify continuity with another statement.')
        except ValueError as error:
            st.error(str(error))
        except Exception:
            st.error('Cannot analyze this workbook. Check its format and supported summary layout.')

    st.header('📊 Multi-Decompte Analysis')
    st.caption(f'Upload 2–{MAX_FILES} consecutive statements from one project (50 MiB total). '
               'Statement identity comes from the source heading or explicit metadata; filename numbers are cross-checked.')
    multi_files = st.file_uploader('Upload several synthetic decompte Excel files', type=['xlsx'],
                                   accept_multiple_files=True, key='multi_decompte_upload')
    if multi_files:
        batch = audit_batch([(file.name, file) for file in multi_files], policy)
        if batch.records:
            st.subheader('Automatic Financial Comparison')
            st.dataframe(display_frame(batch.records), hide_index=True, width='stretch')
        st.subheader('Financial Continuity Audit')
        if batch.comparisons:
            st.dataframe(display_frame(batch.comparisons), hide_index=True, width='stretch')
        a, b, c = st.columns(3)
        a.metric('Inputs Received', batch.requested)
        b.metric('Inputs Parsed', len(batch.records))
        c.metric('Continuity Checks Passed', sum(row['Status'] == 'OK' for row in batch.comparisons))
        if batch.status == 'OK':
            st.success('All uploaded statements and all continuity checks passed under the displayed assumptions.')
        else:
            st.warning('Audit incomplete or requires review. No overall pass is confirmed.')
            for issue in batch.issues:
                st.write(f'• {issue}')
        st.caption('Differences require source verification and do not establish accounting errors.')
