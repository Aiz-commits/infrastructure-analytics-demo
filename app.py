"""Public synthetic demo. Uploaded workbooks stay in the current session's memory."""
import hashlib
from datetime import datetime, timezone
from io import BytesIO
from decimal import Decimal
import altair as alt
import pandas as pd
import streamlit as st
from scripts.ai_reader import read_with_ai
from scripts.ai_writer import Texts, findings_json, write_texts
from scripts.audit import all_passed, audit_batch, display_frame
from scripts.controller_checks import (EXAMPLES_DIR, FIELDS, LABELS, SOURCE_AI, SOURCE_EDITED, SOURCE_PDF_TEXT,
                                       SOURCE_VISION, apply_edits, from_extractor, parse_edits,
                                       previous_from_history, review_count, run_checks)
from scripts.controller_review import email_eml, memo_markdown, trail_row
from scripts.decompte_extractor import extract_decompte
from scripts.documents import check_limits, detect_kind
from ui.document_section import (AI_CALL_LIMIT, UNAVAILABLE, NotCached, ai_call_allowed, read_document,
                                 upload_problem)
from scripts.policy import load_policy
from scripts.reports import REPORT_NAMES, verified_report
from scripts.workbooks import MAX_FILES, preview_workbook, workbook_bytes
from ui.history_section import mark_values_edited, render_public_history, save_decision

CONTROLLER_PAGE = '🤖 AI Controller'
st.set_page_config(page_title='Construction Project Monitoring', page_icon='🏗️', layout='wide')
st.sidebar.title('🏗️ Infrastructure Analytics Demo')
st.sidebar.caption('Construction Monitoring System')
page = st.sidebar.radio('Go to', ['Overview', 'Financial Audit', 'Technical Monitoring', 'Document Analysis', 'Report Center',
                                  CONTROLLER_PAGE])
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


PRIVACY_TEXT = ('This file contains no confidential data. It will be sent to Google Gemini (free tier), '
                'which may use it to improve its products.')
ICONS = {'OK': '✅ OK', 'WARNING': '⚠️ WARNING', 'REVIEW': '⚠️ REVIEW', 'SKIPPED': '⏭️ SKIPPED'}
AI_SOURCES = (SOURCE_AI, SOURCE_PDF_TEXT, SOURCE_VISION)
VISION_NOTICE = ('These numbers were typed by the AI from the picture. '
                 'Compare each one with the document before confirming.')



def gemini_key():
    try:
        return st.secrets.get('GEMINI_API_KEY') or None
    except Exception:  # No secrets file locally or in CI: template mode.
        return None



@st.cache_data(show_spinner=False, max_entries=100)
def cached_ai_read(digest, _data, _key):
    statement = read_with_ai(_data, _key)
    if statement is None:
        raise NotCached()
    return statement


@st.cache_data(show_spinner=False, max_entries=200)
def cached_texts(digest, language, payload, _findings, _key, project, number):
    texts = write_texts(_findings, language, policy, _key, project=project, number=number)
    if not texts.ai_used:
        raise NotCached()
    return texts


def set_source(name, data, example):
    st.session_state['ctrl_source'] = {'name': name, 'data': data, 'example': example,
                                       'digest': hashlib.sha256(data).hexdigest()}


def read_values(source, key, allow_ai):
    """-> (statement, problem, read_method)."""
    kind = detect_kind(source['data'])
    check_limits(kind, source['data'])
    if kind != 'xlsx':
        return read_document(source, kind, key, allow_ai)
    statement, problem = read_workbook(source, key, allow_ai)
    return statement, problem, None


def read_workbook(source, key, allow_ai):
    data = source['data']
    workbook_bytes(data)
    try:
        return from_extractor(extract_decompte(data, policy=policy)), None
    except ValueError:
        pass
    if not allow_ai:
        return None, 'Layout not supported by the fixed reader. Tick the privacy box above to allow AI reading.'
    if not key:
        return None, 'Layout not supported by the fixed reader, and AI is offline (template mode). Use a standard-layout décompte.'
    cache_key = (source['digest'], 'read')
    if cache_key in st.session_state.setdefault('ctrl_ai_failed', set()):
        return None, UNAVAILABLE
    if not ai_call_allowed(cache_key):
        return None, f'AI limit reached for this session ({AI_CALL_LIMIT} calls). Use a standard-layout décompte.'
    try:
        with st.spinner('Gemini is locating the values…'):
            return cached_ai_read(source['digest'], data, key), None
    except NotCached:
        st.session_state['ctrl_ai_failed'].add(cache_key)
        return None, UNAVAILABLE


def values_frame(statement):
    return pd.DataFrame([{'Field': LABELS[f], 'Value DH': None if v.value is None else float(v.value),
                          'Cell': v.cell or 'not found', 'Source': v.source, 'Uncertain': 'yes' if v.uncertain else ''}
                         for f, v in ((f, statement.values[f]) for f in FIELDS)])


def confirm_values(statement, digest, source=None):
    confirmed = st.session_state.setdefault('ctrl_confirmed', {})
    if digest in confirmed:
        return confirmed[digest]
    st.warning('Some values were found by AI. Check them, correct them if needed, then click Confirm. '
               'No check runs before you confirm.')
    sources = {v.source for v in statement.values.values()}
    if SOURCE_VISION in sources:
        st.warning(VISION_NOTICE)
        if source is not None and detect_kind(source['data']) in ('jpeg', 'png'):
            st.image(source['data'], caption=source['name'], width=520)
        else:
            st.caption('PDF page sent to AI')
    elif SOURCE_PDF_TEXT in sources:
        st.caption('Values marked "PDF text (AI located)" were matched by Gemini; Python read each number from '
                   'the PDF text itself. Uncertain = the line or column header label does not match.')
    else:
        st.caption('Values marked "found by AI" were located by Gemini; Python read each one from its cell. '
                   'Uncertain = the row or column label does not match.')
    edited = st.data_editor(values_frame(statement), disabled=['Field', 'Cell', 'Source', 'Uncertain'],
                            hide_index=True, width='stretch', key=f'ctrl_editor_{digest[:12]}')
    a, b = st.columns(2)
    project = a.text_input('Project', value=statement.project, key=f'ctrl_project_{digest[:12]}')
    number = b.number_input('Statement number', min_value=0, max_value=10000, step=1,
                            value=statement.number or 0, key=f'ctrl_number_{digest[:12]}')
    if not st.button('Confirm values', key='ctrl_confirm', type='primary'):
        return None
    edits, bad = parse_edits(dict(zip(FIELDS, edited['Value DH'].tolist())))
    if bad:
        st.error('Not a valid amount: ' + ', '.join(LABELS[f] for f in bad) +
                 '. Type digits only, with a dot for decimals (e.g. 900000.00), or leave the cell empty.')
        return None
    confirmed[digest] = apply_edits(statement, edits, project=project.strip(), number=int(number) or None)
    result = confirmed[digest]
    if (any(v.source == SOURCE_EDITED for v in result.values.values())
            or (result.project, result.number) != (statement.project, statement.number)):
        mark_values_edited(digest)
    return result


def previous_values(source, previous_upload):
    if source['example']:
        return previous_from_history(st.session_state['ctrl_statement'])
    if previous_upload is None:
        return None
    try:
        return from_extractor(extract_decompte(workbook_bytes(previous_upload), policy=policy))
    except ValueError as error:
        st.warning(f'Previous décompte not used: {error}')
        return None


def findings_frame(findings):
    return pd.DataFrame([{'Check': f.title, 'Status': ICONS[f.severity],
                          'Difference DH': '' if f.difference is None else f'{f.difference:,.2f}',
                          'Evidence': f.evidence} for f in findings])


def review_texts(texts, source, statement, tag):
    memo = st.text_area('📝 Audit memo', texts.memo, height=280, key=f'ctrl_memo_{tag}')
    subject = st.text_input('✉️ Email subject', texts.email_subject, key=f'ctrl_subject_{tag}')
    body = st.text_area('✉️ Email to contractor', texts.email_body, height=280, key=f'ctrl_body_{tag}')
    a, b = st.columns(2)
    clicked = 'Approved' if a.button('✅ Approve', key='ctrl_approve') else None
    clicked = 'Rejected' if b.button('❌ Reject', key='ctrl_reject') else clicked
    decisions = st.session_state.setdefault('ctrl_decisions', {})
    new_click = None
    if clicked:
        now = datetime.now(timezone.utc)
        decisions[tag] = (clicked, Texts(memo, subject, body, texts.ai_used), now)
        new_click = decisions[tag]
        st.session_state.setdefault('ctrl_trail', []).append(trail_row(source['name'], now, texts.ai_used, clicked))
    if tag not in decisions:
        return None, None
    decision, final, now = decisions[tag]
    if decision == 'Rejected':
        st.info(f'Rejected by reviewer — {now:%Y-%m-%d %H:%M UTC}. Nothing was sent.')
        return decision, new_click
    st.success(f'Approved by reviewer — {now:%Y-%m-%d %H:%M UTC}. Nothing was emailed; download the files below.')
    stem = f'D{statement.number}' if statement.number else 'decompte'
    c, d = st.columns(2)
    c.download_button('⬇ memo.md', memo_markdown(final, statement.project, statement.number, decision, now),
                      file_name=f'audit_memo_{stem}.md', mime='text/markdown', key='ctrl_dl_memo')
    d.download_button('⬇ email.eml', email_eml(final, now), file_name=f'email_{stem}.eml',
                      mime='message/rfc822', key='ctrl_dl_eml')
    return decision, new_click


def controller_page():
    st.header(CONTROLLER_PAGE)
    st.caption('A digital junior auditor. Python does every calculation; the AI only locates cells and drafts text. '
               'A human approves. Nothing is emailed.')
    key = gemini_key()
    language = 'fr' if st.selectbox('Language', ['Français', 'English'], key='ctrl_lang') == 'Français' else 'en'
    if not key:
        st.info('AI offline — template mode')
    progress = st.empty()
    steps = {'Receive': '⏳', 'Read': '⏳', 'Check': '⏳', 'Explain': '⏳', 'Review': '⏳'}
    show = lambda: progress.markdown('  '.join(f'**Step {i} {name}** {mark}' for i, (name, mark) in
                                               enumerate(steps.items(), start=1)))
    a, b = st.columns(2)
    if a.button('▶ Try example: DEMO_DP_N5', key='ctrl_example'):
        set_source('DEMO_DP_N5.xlsx', (EXAMPLES_DIR / 'DEMO_DP_N5.xlsx').read_bytes(), True)
    if b.button('▶ Try example: new layout (AI reading)', key='ctrl_example_new'):
        set_source('DEMO_DP_N5_NEW_LAYOUT.xlsx', (EXAMPLES_DIR / 'DEMO_DP_N5_NEW_LAYOUT.xlsx').read_bytes(), True)
    c, d = st.columns(2)
    if c.button('▶ Try example: PDF', key='ctrl_example_pdf'):
        set_source('DEMO_DP_N5.pdf', (EXAMPLES_DIR / 'DEMO_DP_N5.pdf').read_bytes(), True)
    if d.button('▶ Try example: photo', key='ctrl_example_photo'):
        set_source('DEMO_DP_N5_PHOTO.jpg', (EXAMPLES_DIR / 'DEMO_DP_N5_PHOTO.jpg').read_bytes(), True)
    uploaded = st.file_uploader('Or upload your own synthetic décompte (.xlsx, .pdf, .jpg, .png)',
                                type=['xlsx', 'pdf', 'jpg', 'jpeg', 'png'], key='ctrl_upload')
    privacy = st.checkbox(PRIVACY_TEXT, key='ctrl_privacy')
    previous_upload = st.file_uploader('Optional: the previous décompte, for continuity and sequence checks',
                                       type=['xlsx'], key='ctrl_prev_upload')
    if uploaded is not None:
        data = uploaded.getvalue()
        digest = hashlib.sha256(data).hexdigest()
        problem = upload_problem(data)
        if problem:
            st.error(problem)
            show()
            return
        if st.session_state.get('ctrl_upload_digest') != digest:
            st.session_state['ctrl_upload_digest'] = digest
            set_source(uploaded.name, data, False)
    source = st.session_state.get('ctrl_source')
    if source is None:
        show()
        return
    steps['Receive'] = '✅'
    allow_ai = bool(source['example'] or privacy)
    st.caption(f"File: {source['name']}" + ('' if allow_ai else ' • AI disabled until you tick the privacy box'))
    try:
        statement, problem, read_method = read_values(source, key, allow_ai)
    except ValueError as error:
        statement, problem, read_method = None, str(error), None
    if statement is None:
        steps['Read'] = '⚠️'
        show()
        st.warning(problem)
        return
    if any(v.source in AI_SOURCES for v in statement.values.values()):
        statement = confirm_values(statement, source['digest'], source)
        if statement is None:
            show()
            return
    steps['Read'] = '✅'
    st.session_state['ctrl_statement'] = statement
    st.subheader('Values read')
    st.dataframe(values_frame(statement), hide_index=True, width='stretch')
    findings = run_checks(statement, previous_values(source, previous_upload), policy)
    # First time the checks were shown for this file and language: start of 'time to decision' (Phase 2.5).
    opened_at = st.session_state.setdefault('ctrl_opened', {}).setdefault(
        f'{source["digest"][:12]}_{language}', datetime.now(timezone.utc))
    steps['Check'] = '⚠️' if review_count(findings) else '✅'
    st.subheader('Checks')
    st.dataframe(findings_frame(findings), hide_index=True, width='stretch')
    texts, cache_key = None, (source['digest'], language)
    if key and allow_ai:
        failed = st.session_state.setdefault('ctrl_ai_failed', set())
        if cache_key in failed:
            st.caption('AI text unavailable or failed the number check; template text shown.')
        elif ai_call_allowed(cache_key):
            payload = findings_json(findings, statement.project, statement.number)
            try:
                with st.spinner('Gemini is drafting the memo and email…'):
                    texts = cached_texts(source['digest'], language, payload, findings, key,
                                         statement.project, statement.number)
            except NotCached:
                failed.add(cache_key)
                st.caption('AI text unavailable or failed the number check; template text shown.')
        else:
            st.caption(f'AI limit reached for this session ({AI_CALL_LIMIT} calls); template text shown.')
    if texts is None:
        texts = write_texts(findings, language, policy, None, project=statement.project, number=statement.number)
    steps['Explain'] = '✅'
    st.caption('Drafted by AI (number-checked)' if texts.ai_used else 'Template text (no AI)')
    decision, new_click = review_texts(texts, source, statement, f'{source["digest"][:12]}_{language}')
    if new_click:
        clicked, final, decided_at = new_click
        ai_read = any(v.source in (SOURCE_AI, SOURCE_EDITED) for v in statement.values.values())
        read_method = read_method or ('found by AI' if ai_read else 'fixed layout')
        save_decision(source=source, statement=statement, findings=findings, app_texts=texts, final_texts=final,
                      decision=clicked, decided_at=decided_at, opened_at=opened_at, language=language,
                      read_method=read_method, rule_version=policy.version)
    steps['Review'] = {'Approved': '✅', 'Rejected': '❌'}.get(decision, '⏳')
    show()
    trail = st.session_state.get('ctrl_trail', [])
    if trail:
        st.subheader('Audit trail (this session)')
        st.dataframe(pd.DataFrame(trail), hide_index=True, width='stretch')


if page == CONTROLLER_PAGE:
    try:
        controller_page()
    except Exception:
        st.error('Cannot analyze this workbook. Check its format, or try a standard-layout décompte.')
    try:
        render_public_history()
    except Exception:
        st.info('Public history is temporarily unavailable.')
elif page != 'Document Analysis':
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
