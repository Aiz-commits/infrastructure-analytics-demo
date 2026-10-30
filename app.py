
from pathlib import Path
import altair as alt
import streamlit as st
import pandas as pd
from scripts.decompte_extractor import extract_decompte
st.set_page_config(
    page_title="Construction Project Monitoring",
    page_icon="🏗️",
    layout="wide"
)

BASE = Path(__file__).resolve().parent
OUTPUTS = BASE / "outputs"


# ------------------------------------------
# APPLICATION SIDEBAR
# ------------------------------------------

st.sidebar.title("🏗️ 	Infrastructure Analytics Demo")
st.sidebar.caption("Construction Monitoring System")

st.sidebar.divider()

st.sidebar.markdown("### Navigation")

page = st.sidebar.radio(
    "Go to",
    [
        "Overview",
        "Financial Audit",
        "Technical Monitoring",
        "Document Analysis",
        "Report Center"
    ],
    label_visibility="collapsed"
)


st.sidebar.info(
    "Financial monitoring, technical auditing, "
    "document analysis and reporting."
)

st.sidebar.divider()

st.sidebar.caption(
    "Demo Infrastructure Project | Internship Project | 2026"
)

st.title("🏗️ 	Infrastructure Analytics Demo | Project Monitoring")
st.info(
    "DEMO VERSION — Financial and technical data are synthetic. "
    "This application does not contain confidential company documents."
)
st.caption(
    "Demo Infrastructure Project | Roadworks & Drainage | Financial & Technical Monitoring"
)

financial_file = OUTPUTS / "financial_analysis.xlsx"

if not financial_file.exists():
    st.error("Financial data file not found.")
    st.stop()

df = pd.read_excel(financial_file)

contract_ttc = 5_400_000.00
cumulative_ht = float(df["Cumul actuel HT"].iloc[-1])
valuation_ratio = cumulative_ht * 1.20 / contract_ttc

overview_container = st.container()
if page == "Overview":
    st.subheader("Financial Overview")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Cumulative Works (DH HT)",
        f"{cumulative_ht:,.2f}"
    )

    col2.metric(
        "Contract After Amendment (DH TTC)",
        f"{contract_ttc:,.2f}"
    )

    col3.metric(
        "Indicative Contract Valuation",
        f"{valuation_ratio:.2%}"
    )

    st.info(
        "This is an interim financial analysis. "
        "The project is still ongoing. "
        "The valuation ratio is not physical construction progress."
    )

    st.subheader("Cumulative Financial Evolution")
    chart_data = df[["Decompte", "Cumul actuel HT"]].copy()

    chart = (
        alt.Chart(chart_data)
        .mark_line(point=True, strokeWidth=3)
        .encode(
            x=alt.X("Decompte:N", title="Décompte"),
            y=alt.Y(
                "Cumul actuel HT:Q",
                title="Cumulative Works (DH HT)",
                scale=alt.Scale(domainMin=0),
                axis=alt.Axis(format=",.0f")
            ),
            tooltip=[
                alt.Tooltip("Decompte:N", title="Décompte"),
                alt.Tooltip(
                    "Cumul actuel HT:Q",
                    title="Cumulative Works (DH HT)",
                    format=",.2f"
                )
            ]
        )
        .properties(height=350)
    )

    st.altair_chart(chart, width="stretch")

    st.subheader("Works Recorded per Decompte")
    monthly_data = df[["Decompte", "Travaux du mois HT"]].copy()

    monthly_chart = (
        alt.Chart(monthly_data)
        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
        .encode(
            x=alt.X("Decompte:N", title="Décompte"),
            y=alt.Y(
                "Travaux du mois HT:Q",
                title="Monthly Works (DH HT)",
                scale=alt.Scale(domainMin=0),
                axis=alt.Axis(format=",.0f")
            ),
            tooltip=[
                alt.Tooltip("Decompte:N", title="Décompte"),
                alt.Tooltip(
                    "Travaux du mois HT:Q",
                    title="Monthly Works (DH HT)",
                    format=",.2f"
                )
            ]
        )
        .properties(height=350)
    )

    st.altair_chart(monthly_chart, width="stretch")

    st.subheader("Financial Data")
    st.dataframe(
        df,
        column_config={
            "Cumul actuel HT": st.column_config.NumberColumn(
                "Cumulative Works (DH HT)", format="%.2f"
            ),
            "Cumul precedent HT": st.column_config.NumberColumn(
                "Previous Cumulative (DH HT)", format="%.2f"
            ),
            "Travaux du mois HT": st.column_config.NumberColumn(
                "Monthly Works (DH HT)", format="%.2f"
            ),
        },
        hide_index=True,
        width="stretch"
    )

    st.caption(
        "Source: Provisional décomptes D1-D4. "
        "Financial continuity and technical quantities "
        "require separate verification."
    )

# ------------------------------------------
# FINANCIAL AUDIT SECTION
# ------------------------------------------
if page == "Financial Audit":
    st.divider()
    st.header("🔍 Financial Audit")

    audit_file = OUTPUTS / "financial_audit.xlsx"
    tax_file = OUTPUTS / "verification_retention_tva.xlsx"

    if audit_file.exists() and tax_file.exists():

        continuity = pd.read_excel(audit_file)
        taxes = pd.read_excel(tax_file)
        taxes.columns = taxes.columns.astype(str).str.strip(
        ).str.replace("D?compte", "Décompte", regex=False)
        taxes = taxes[
            taxes["Décompte"].astype(str).str.match(r"^D[1-4]\s*-", na=False)
        ].copy()

        st.subheader("Cumulative Continuity Checks")
        st.dataframe(
            continuity,
            use_container_width=True,
            hide_index=True
        )

        issues = continuity[
            continuity["Status"] == "CHECK"
        ]

        if len(issues) > 0:
            st.warning(
                f"{len(issues)} financial continuity "
                "record(s) require verification."
            )
        else:
            st.success(
                "All cumulative continuity checks passed."
            )

        st.subheader("Retention, VAT and TTC Verification")
        st.dataframe(
            taxes,
            use_container_width=True,
            hide_index=True
        )

        st.caption(
            "Audit alerts indicate records to investigate, "
            "not confirmed accounting errors."
        )

    else:
        st.info(
            "Financial audit files are not available yet."
        )

# ------------------------------------------
# TECHNICAL MONITORING SECTION
# ------------------------------------------
if page == "Technical Monitoring":
    st.divider()
    st.header("🏗️ Technical Monitoring")

    technical_file = OUTPUTS / "audit_technique_valide.xlsx"

    if technical_file.exists():

        technical = pd.read_excel(
            technical_file,
            sheet_name="Controle_D3_D4"
        )

        # Category names
        category_names = {
            "ATT VR IS": "Roadworks (VR)",
            "ATT EP IS": "Stormwater Drainage (EP)",
            "ATT EU IS": "Wastewater Drainage (EU)"
        }

        st.subheader("Construction Quantity Audit")

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Work Items Examined",
            len(technical)
        )

        col2.metric(
            "Passed Checks",
            (technical["Statut validation"] == "OK").sum()
        )

        col3.metric(
            "Records Requiring Review",
            (technical["Statut validation"] != "OK").sum()
        )

        selected_category = st.selectbox(
            "Select Construction Category",
            options=list(category_names.keys()),
            format_func=lambda x: category_names[x]
        )

        filtered = technical[
            technical["Categorie"] == selected_category
        ]

        st.subheader(
            f"Quantity Monitoring — {category_names[selected_category]}"
        )

        st.dataframe(
            filtered,
            use_container_width=True,
            hide_index=True
        )

        st.subheader("Validation Status Distribution")

        status_counts = (
            filtered["Statut validation"]
            .value_counts()
        )

        st.bar_chart(status_counts)

        st.caption(
            "Automated preliminary screening of D3-D4 in-site "
            "attachements. Flags require source verification; "
            "they are not confirmed construction errors."
        )

    else:
        st.info(
            "Technical validation data not found. "
            "Run validate_technical_audit.py first."
        )

# ------------------------------------------
# REPORT DOWNLOAD CENTER
# ------------------------------------------

if page == "Report Center":
    st.divider()
    st.header("📥 Report Download Center")

    st.write(
        "Download the financial and technical audit reports "
        "generated by the Python analysis system."
    )

    reports = {
        "Consolidated Financial Audit":
            "rapport_audit_financier.xlsx",

        "Financial Calculation Verification":
            "verification_calculs.xlsx",

        "Retention, VAT and TTC Audit":
            "verification_retention_tva.xlsx",

        "Technical Quantity Audit":
            "audit_technique_valide.xlsx"
    }

    for label, filename in reports.items():
        path = OUTPUTS / filename

        if path.exists():
            with open(path, "rb") as file:
                st.download_button(
                    label=f"⬇️ Download {label}",
                    data=file.read(),
                    file_name=filename,
                    mime=(
                        "application/vnd.openxmlformats-"
                        "officedocument.spreadsheetml.sheet"
                    ),
                    key=filename
                )
        else:
            st.warning(f"Missing report: {filename}")

    st.caption(
        "Reports reflect the current local analysis files. "
        "They are not automatically refreshed when a new "
        "décompte becomes available."
    )

# ------------------------------------------
# EXCEL DOCUMENT IMPORT
# ------------------------------------------
if page == "Document Analysis":
    st.divider()
    st.header("📤 Excel Document Import")

    st.write(
        "Upload an Excel décompte to inspect its worksheets "
        "and prepare it for financial and technical analysis."
    )

    uploaded_file = st.file_uploader(
        "Choose an Excel document",
        type=["xlsx"],
        key="decompte_upload"
    )

    if uploaded_file is not None:

        try:
            excel = pd.ExcelFile(uploaded_file)

            st.success(
                f"File loaded successfully: {uploaded_file.name}"
            )

            st.subheader("Available Worksheets")

            selected_sheet = st.selectbox(
                "Select Worksheet",
                excel.sheet_names
            )

            preview = pd.read_excel(
                excel,
                sheet_name=selected_sheet,
                header=None
            )

            # Remove completely empty rows and columns
            preview = preview.dropna(how="all")
            preview = preview.dropna(axis=1, how="all")

            # Prevent mixed Excel values from causing errors
            preview = preview.astype(str)

            st.subheader("Worksheet Preview")

            st.dataframe(
                preview.head(30),
                width="stretch"
            )

            st.info(
                "This is a read-only preview. "
                "Automatic extraction and validation "
                "will be connected in the next development stage."
            )

            # Automatic financial analysis of uploaded decompte
            st.subheader("Automatic Financial Verification")

            if any(name.upper().startswith("DP") for name in excel.sheet_names):
                from io import BytesIO

                result = extract_decompte(
                    BytesIO(uploaded_file.getvalue())
                )

                col_a, col_b, col_c = st.columns(3)

                col_a.metric(
                    "Executed Works (DH HT)",
                    f"{result['Works HT']:,.2f}"
                )

                col_b.metric(
                    "Retention (DH)",
                    f"{result['Retention']:,.2f}"
                )

                col_c.metric(
                    "Total TTC (DH)",
                    f"{result['TTC']:,.2f}"
                )

                if result["Status"] == "OK":
                    st.success(
                        "Financial calculations verified successfully."
                    )
                else:
                    st.warning(
                        "Financial calculations require verification."
                    )

                st.dataframe(
                    pd.DataFrame([result]),
                    hide_index=True,
                    width="stretch"
                )
            else:
                st.warning(
                    "No DP summary worksheet found."
                )

        except Exception as error:
            st.error(
                f"Unable to read this Excel document: {error}"
            )


# ------------------------------------------
# MULTI-DECOMPTE ANALYSIS
# ------------------------------------------
if page == "Document Analysis":
    st.divider()
    st.header("📊 Multi-Decompte Analysis")

    multi_files = st.file_uploader(
        "Upload several decompte Excel files",
        type=["xlsx"],
        accept_multiple_files=True,
        key="multi_decompte_upload"
    )

    if multi_files:
        st.success(
            f"{len(multi_files)} Excel document(s) selected."
        )

        st.write("Selected files:")

        for uploaded in multi_files:
            st.write(f"• {uploaded.name}")

        # Analyze each uploaded decompte
        from io import BytesIO

        results = []

        for uploaded in multi_files:
            try:
                result = extract_decompte(
                    BytesIO(uploaded.getvalue())
                )

                result["File"] = uploaded.name
                results.append(result)

            except Exception as error:
                st.error(
                    f"Cannot analyze {uploaded.name}: {error}"
                )

        if results:
            comparison = pd.DataFrame(results)

            st.subheader("Automatic Financial Comparison")

            st.dataframe(
                comparison,
                hide_index=True,
                width="stretch"
            )

            st.subheader("Executed Works by Uploaded File")

            st.bar_chart(
                comparison.set_index("File")["Works HT"]
            )

            passed = (
                comparison["Status"] == "OK"
            ).sum()

            st.success(
                f"{passed} out of {len(comparison)} "
                "uploaded documents passed the arithmetic checks."
            )

            # Financial continuity verification
            st.subheader("Financial Continuity Audit")

            # Identify decompte number from worksheet or filename
            import re

            def get_number(filename):
                match = re.search(
                    r"(?:DP|DECOMPTE)[^\d]*N?[°º#\s]*(\d+)",
                    filename.upper()
                )
                return int(match.group(1)) if match else None

            comparison["Number"] = comparison["File"].apply(
                get_number
            )

            ordered = comparison.dropna(
                subset=["Number"]
            ).sort_values("Number")

            continuity_results = []

            for i in range(1, len(ordered)):
                previous = ordered.iloc[i - 1]
                current = ordered.iloc[i]

                # Check for missing intermediate decompte
                previous_number = int(previous["Number"])
                current_number = int(current["Number"])

                if current_number != previous_number + 1:
                    st.warning(
                        f"Missing decompte between D{previous_number} "
                        f"and D{current_number}. "
                        "Continuity cannot be confirmed."
                    )
                    continue

                expected = previous["Cumulative HT"]
                declared = current["Previous cumulative HT"]

                if pd.isna(declared):
                    difference = None
                    status = "MISSING DATA"
                else:
                    difference = round(expected - declared, 2)
                    status = (
                        "OK" if abs(difference) <= 0.01
                        else "REVIEW REQUIRED"
                    )

                continuity_results.append({
                    "Comparison": (
                        f"D{int(previous['Number'])} → "
                        f"D{int(current['Number'])}"
                    ),
                    "Expected Previous HT": expected,
                    "Declared Previous HT": declared,
                    "Difference DH": difference,
                    "Status": status
                })

            continuity_df = pd.DataFrame(
                continuity_results
            )

            st.dataframe(
                continuity_df,
                hide_index=True,
                width="stretch"
            )

            st.caption(
                "Differences require documentary verification. "
                "They do not automatically indicate accounting errors."
            )

        

    # Automatic continuity audit summary
    if "continuity_df" in locals() and "ordered" in locals():
        st.subheader("Audit Summary")
        total_checks = len(continuity_df)
        statuses = continuity_df.get("Status", pd.Series(dtype=str))
        review_count = int((statuses == "REVIEW REQUIRED").sum())
        passed_count = int((statuses == "OK").sum())
        col1, col2, col3 = st.columns(3)
        col1.metric("Continuity Checks", total_checks)
        col2.metric("Passed", passed_count)
        col3.metric("Require Review", review_count)
        numbers = sorted(ordered["Number"].astype(int).unique())
        missing_numbers = (
            sorted(set(range(numbers[0], numbers[-1] + 1)) - set(numbers))
            if numbers else []
        )
        if missing_numbers:
            st.warning("Missing decompte(s): " + ", ".join(f"D{n}" for n in missing_numbers))
        if review_count > 0:
            st.warning(f"{review_count} financial continuity discrepancies require investigation.")
        if total_checks == 0:
            st.info("Upload at least two decompte files for continuity comparisons.")
        elif not missing_numbers and review_count == 0:
            st.success("All available continuity checks passed, with no gaps detected.")
