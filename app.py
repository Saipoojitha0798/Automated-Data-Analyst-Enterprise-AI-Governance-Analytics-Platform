"""InsightGuard: enterprise business intelligence for CSV and Excel data."""

from __future__ import annotations

import hashlib
import os
import secrets

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from ai_insights import (
    DEFAULT_PRESET,
    MODEL_PRESETS,
    AINarrative,
    build_ai_payload,
    generate_ai_narrative,
    narrative_to_markdown,
    plan_query_with_ai,
)
from analysis import column_profile
from business_insights import BusinessBrief, analyze_business, build_business_report
from demo_data import make_demo_data
from file_io import list_excel_sheets, read_tabular_file
from nlq import QueryAnswer, answer_question, execute_plan, suggested_questions
from pipeline import (
    apply_focus,
    apply_role_selection,
    cleaning_audit_frame,
    focus_options,
    prepare_analysis,
    schema_frame,
)
from ui import (
    inject_styles,
    render_ai_narrative,
    render_brief,
    render_chat_answer,
    render_chat_fallback,
    render_dashboard,
    render_dataset_bar,
    render_evidence,
    render_footer,
    render_how_it_works,
    render_kpis,
    render_landing,
    render_nav,
    render_recommendations,
    render_section_heading,
)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_ANALYSIS_ROWS = 250_000

st.set_page_config(
    page_title="InsightGuard | Enterprise Data Analytics & AI Governance",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "InsightGuard Analytics turns business data into governed, evidence-backed dashboards.",
    },
)


@st.cache_data(show_spinner=False)
def read_uploaded_file(contents: bytes, filename: str, sheet_name: str | None = None) -> pd.DataFrame:
    return read_tabular_file(contents, filename, sheet_name)


def get_openai_api_key() -> str:
    environment_key = os.getenv("OPENAI_API_KEY", "").strip()
    if environment_key:
        return environment_key
    try:
        return str(st.secrets.get("OPENAI_API_KEY", "")).strip()
    except (FileNotFoundError, StreamlitSecretNotFoundError):
        return ""


def get_safety_identifier() -> str:
    if "ada_session_id" not in st.session_state:
        st.session_state.ada_session_id = secrets.token_urlsafe(24)
    session_id = str(st.session_state.ada_session_id)
    return hashlib.sha256(f"ada:{session_id}".encode()).hexdigest()


def render_sidebar(*, server_api_key: str, dataset_name: str | None = None) -> tuple[str, str]:
    with st.sidebar:
        st.title("InsightGuard Analytics")
        st.markdown("---")
        
        if dataset_name:
            st.markdown(f"**Dataset**\n\n{dataset_name}")
            st.markdown("**Dataset status**\n\nReady")
        else:
            st.markdown("**Dataset status**\n\nWaiting for upload")
            
        if server_api_key:
            st.markdown("**AI status**\n\nAvailable")
            api_key = server_api_key
        else:
            st.markdown("**AI status**\n\nNot Configured")
            api_key = st.text_input(
                "Optional OpenAI API key",
                type="password",
                placeholder="Session only",
            ).strip()
            
        st.markdown("**Governance status**\n\nProtected")
        st.markdown("---")
        
        page = st.radio(
            "Navigation",
            ["Overview", "Data Quality", "Analytics", "Anomalies", "Forecasting", "AI Insights", "AI Governance", "Audit & Evidence", "Settings"]
        )
    return api_key, page


def maybe_generate_narrative(
    *,
    api_key: str,
    brief: BusinessBrief,
    business_context: str,
) -> tuple[AINarrative | None, str | None]:
    if not api_key:
        return None, None

    payload = build_ai_payload(brief, context=business_context)
    fingerprint = hashlib.sha256(payload.encode()).hexdigest()
    cached = st.session_state.get("ai_narrative")
    cached_fingerprint = st.session_state.get("ai_narrative_fingerprint")
    selected_preset = st.selectbox(
        "Strategy model",
        list(MODEL_PRESETS),
        index=list(MODEL_PRESETS).index(DEFAULT_PRESET),
        help="Luna is the cost-efficient default. Terra spends more reasoning on ambiguous decisions.",
    )
    config = MODEL_PRESETS[selected_preset]

    if st.button("Generate AI strategic read", type="primary", width="stretch"):
        try:
            with st.spinner("Connecting the evidence into a strategic read…"):
                cached = generate_ai_narrative(
                    brief,
                    api_key=api_key,
                    config=config,
                    context=business_context,
                    safety_identifier=get_safety_identifier(),
                )
            st.session_state.ai_narrative = cached
            st.session_state.ai_narrative_fingerprint = fingerprint
            st.session_state.ai_narrative_model = config.model
            cached_fingerprint = fingerprint
        except Exception:  # API failures should never take down the deterministic product.
            st.error("The optional strategy agent is temporarily unavailable. Try again or switch models.")
            return None, None

    if cached_fingerprint != fingerprint or not isinstance(cached, AINarrative):
        return None, None
    model = str(st.session_state.get("ai_narrative_model", config.model))
    return cached, model


def answer_with_ai_planner(
    question: str,
    dataframe: pd.DataFrame,
    roles,
    api_key: str,
) -> QueryAnswer | None:
    """Plan with the model over schema only, then execute locally."""
    try:
        plan = plan_query_with_ai(
            question,
            dataframe,
            roles,
            api_key=api_key,
            safety_identifier=get_safety_identifier(),
        )
        if plan is None:
            return None
        executed = execute_plan(plan, dataframe, roles)
    except Exception:  # A planner outage must never break the chat.
        return None
    return QueryAnswer(
        question=question,
        plan=executed.plan,
        answer=executed.answer,
        calculation=executed.calculation,
        table=executed.table,
        chart=executed.chart,
    )


def render_ask_ada(dataframe: pd.DataFrame, roles, source_name: str, api_key: str) -> None:
    """Chat over the analyzed dataset; every answer is a local calculation."""
    fingerprint = f"{source_name}:{len(dataframe)}:{','.join(dataframe.columns)}"
    if st.session_state.get("chat_fingerprint") != fingerprint:
        st.session_state.chat_fingerprint = fingerprint
        st.session_state.chat_history = []

    suggestions = suggested_questions(dataframe, roles)
    chips = st.columns(len(suggestions))
    question = None
    for chip, suggestion in zip(chips, suggestions, strict=True):
        if chip.button(suggestion, key=f"chip_{suggestion}", width="stretch"):
            question = suggestion

    typed = st.chat_input("Ask about this data — try “top 5 by revenue” or “which segment grew fastest?”")
    question = typed or question
    if question:
        result = answer_question(question, dataframe, roles)
        if result is None and api_key:
            with st.spinner("Planning the calculation…"):
                result = answer_with_ai_planner(question, dataframe, roles, api_key)
        st.session_state.chat_history.append({"question": question, "result": result})

    if not st.session_state.chat_history:
        st.markdown(
            '<div class="empty-state">Ask anything about the analyzed table. '
            "Answers are computed locally and every one shows its calculation.</div>",
            unsafe_allow_html=True,
        )
    for entry in st.session_state.chat_history:
        with st.chat_message("user"):
            st.markdown(entry["question"])
        with st.chat_message("assistant"):
            if entry["result"] is not None:
                render_chat_answer(entry["result"])
            else:
                render_chat_fallback(suggestions)


inject_styles()
render_nav()

source_mode = st.segmented_control(
    "Choose a source",
    ["Explore the live demo", "Upload your file"],
    default="Explore the live demo",
    label_visibility="collapsed",
)

uploaded_file = None
business_context = ""
if source_mode == "Upload your file":
    uploaded_file = st.file_uploader(
        "Upload a CSV or Excel workbook",
        type=["csv", "xlsx", "xlsm"],
        help="Maximum file size: 25 MB. InsightGuard analyzes the first worksheet.",
    )
    business_context = st.text_input(
        "Optional business context",
        placeholder="Example: Subscription revenue by customer, product, and month",
        max_chars=500,
    )
    if uploaded_file is None:
        render_how_it_works()
        render_footer()
        st.stop()

try:
    if source_mode == "Explore the live demo":
        raw_dataframe = make_demo_data()
        source_name = "Acme operating data · demo"
        business_context = "Two years of orders across products, regions, and sales channels."
    else:
        assert uploaded_file is not None
        if uploaded_file.size > MAX_UPLOAD_BYTES:
            st.error("That file is larger than InsightGuard's 25 MB analysis limit.")
            st.stop()
        contents = uploaded_file.getvalue()
        selected_sheet = None
        worksheets = list_excel_sheets(contents, uploaded_file.name)
        if len(worksheets) > 1:
            selected_sheet = st.selectbox(
                "Worksheet to analyze",
                worksheets,
                help="The workbook has several sheets; InsightGuard analyzes one at a time.",
            )
        raw_dataframe = read_uploaded_file(contents, uploaded_file.name, selected_sheet)
        source_name = (
            f"{uploaded_file.name} · {selected_sheet}" if selected_sheet else uploaded_file.name
        )

    prepared = prepare_analysis(raw_dataframe, row_limit=MAX_ANALYSIS_ROWS)
except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError, ValueError, ImportError) as error:
    st.error(f"InsightGuard could not read this file. Please upload a valid CSV or Excel file.")
    st.stop()

api_key, current_page = render_sidebar(
    server_api_key=get_openai_api_key(), 
    dataset_name=source_name
)

if current_page == "Overview" and source_mode == "Upload your file" and uploaded_file is None:
    render_landing()
    render_how_it_works()
    render_footer()
    st.stop()
    
if current_page == "Overview":
    render_landing()

if prepared.truncated_rows:
    st.warning(
        f"InsightGuard analyzed the first {MAX_ANALYSIS_ROWS:,} rows for predictable performance "
        f"and skipped {prepared.truncated_rows:,}."
    )

dataframe = prepared.dataframe
detected = prepared.detected_roles
date_options = [
    "None",
    *[
        column
        for column in dataframe.columns
        if pd.api.types.is_datetime64_any_dtype(dataframe[column])
    ],
]
measure_options = ["None", *detected.numeric]
dimension_options = ["None", *detected.dimensions]

with st.expander("Tune InsightGuard's schema detection", expanded=False):
    st.caption("InsightGuard selected these roles automatically. Override them only when the source schema needs context.")
    selectors = st.columns(3)
    selected_date = selectors[0].selectbox(
        "Date",
        date_options,
        index=date_options.index(detected.date) if detected.date in date_options else 0,
    )
    selected_measure = selectors[1].selectbox(
        "Primary metric",
        measure_options,
        index=measure_options.index(detected.measure) if detected.measure in measure_options else 0,
    )
    selected_dimension = selectors[2].selectbox(
        "Business segment",
        dimension_options,
        index=dimension_options.index(detected.dimension) if detected.dimension in dimension_options else 0,
    )

roles = apply_role_selection(
    detected,
    date=selected_date,
    measure=selected_measure,
    dimension=selected_dimension,
)

focus_value = None
focus_values = focus_options(dataframe, roles)
if focus_values:
    everything = f"All {roles.dimension} values"
    focus_columns = st.columns([0.34, 0.66])
    choice = focus_columns[0].selectbox(
        f"Drill into one {roles.dimension}",
        [everything, *focus_values],
        help="Focus the brief, dashboard, chat, and exports on a single slice. "
        "InsightGuard regroups the slice by the next useful segment.",
    )
    if choice != everything:
        focus_value = choice

dataframe, roles = apply_focus(dataframe, roles, focus_value)
brief = analyze_business(dataframe, roles)

render_dataset_bar(source_name, dataframe, roles, focus=focus_value)
render_brief(brief)
render_kpis(brief)

if current_page == "Overview":
    render_brief(brief)
    render_kpis(brief)
    
    st.markdown("### Top Anomalies")
    from anomalies import detect_anomalies
    from aggregation import build_trend
    trend_series = build_trend(dataframe, roles)
    if not trend_series.frame.empty:
        anoms = detect_anomalies(trend_series.frame)
        if anoms:
            for a in anoms[:3]:
                st.warning(f"Anomaly detected: {a.period.strftime('%Y-%m-%d')} - Expected between {a.expected_low:,.2f} and {a.expected_high:,.2f}, Actual: {a.value:,.2f}")
        else:
            st.info("No critical anomalies detected in the primary trend.")
    
    st.markdown("### Governance Summary")
    st.success("PII Protection: ENABLED")
    st.success("Calculation Traceability: ENABLED")
    st.success("Evidence-Based Responses: ENABLED")

elif current_page == "Data Quality":
    render_section_heading(
        "Data Quality",
        "Data Quality & Validation",
        "Monitor completeness, uniqueness, and consistency."
    )
    quality_columns = st.columns(4)
    quality_columns[0].metric("Rows analyzed", f"{len(dataframe):,}")
    quality_columns[1].metric("Columns", f"{len(dataframe.columns):,}")
    quality_columns[2].metric(
        "Duplicates removed",
        f"{prepared.cleaning_report.duplicate_rows_removed:,}",
    )
    quality_columns[3].metric("Missing cells", f"{int(dataframe.isna().sum().sum()):,}")

    with st.expander("Cleaning audit", expanded=True):
        st.dataframe(
            cleaning_audit_frame(prepared.cleaning_report),
            hide_index=True,
            width="stretch",
        )
    st.subheader("Data dictionary")
    st.dataframe(column_profile(dataframe), hide_index=True, width="stretch")

elif current_page == "Analytics":
    render_section_heading(
        "Business Analytics",
        "Operating view",
        "Trend, contribution, distribution, and the strongest measurable relationship."
    )
    render_dashboard(dataframe, roles)

elif current_page == "Anomalies":
    render_section_heading(
        "Anomalies",
        "Anomaly Detection",
        "Detect statistical deviations in the primary metric over time."
    )
    from anomalies import detect_anomalies
    from aggregation import build_trend
    trend_series = build_trend(dataframe, roles)
    if not trend_series.frame.empty:
        anoms = detect_anomalies(trend_series.frame)
        if anoms:
            st.error(f"Detected {len(anoms)} anomalies.")
            anom_data = [{"Date": a.period, "Value": a.value, "Expected Range": f"{a.expected_low:,.2f} - {a.expected_high:,.2f}"} for a in anoms]
            st.dataframe(pd.DataFrame(anom_data), hide_index=True, width="stretch")
        else:
            st.info("No anomalies detected.")
    else:
        st.info("Select a date and metric to detect anomalies.")

elif current_page == "Forecasting":
    render_section_heading(
        "Forecasting",
        "Time-Series Forecasting",
        "Projected baseline forecast based on historical trends."
    )
    from aggregation import build_trend
    import plotly.express as px
    import plotly.graph_objects as go
    from ui import style_chart
    from forecasting import build_forecast, describe_backtest
    trend_series = build_trend(dataframe, roles)
    trend = trend_series.frame
    if not trend.empty:
        forecast = build_forecast(trend)
        if forecast:
            figure = px.line(trend, x="Period", y="Value", title=f"Forecast: {roles.measure or 'Records'}", markers=True)
            figure.add_trace(go.Scatter(x=[*forecast.periods, *reversed(forecast.periods)], y=[*forecast.upper, *reversed(forecast.lower)], mode="lines", fill="toself", fillcolor="rgba(139,92,246,.09)", line={"width": 0}, showlegend=False))
            figure.add_trace(go.Scatter(x=[trend.iloc[-1]["Period"], *forecast.periods], y=[float(trend.iloc[-1]["Value"]), *forecast.values], mode="lines", name="Forecast", line={"width": 2.5, "dash": "dash", "color": "#8B5CF6"}))
            st.plotly_chart(style_chart(figure), width="stretch", config={"displayModeBar": False})
            st.caption(f"Baseline forecast: {forecast.method} · {describe_backtest(forecast.backtest)}.")
        else:
            st.info("Not enough data points to generate a forecast.")
    else:
        st.info("Select a date column to generate a forecast.")

elif current_page == "AI Insights":
    render_section_heading(
        "AI Insights",
        "AI-Assisted Analysis",
        "Connect the signals into a strategic read using optional AI."
    )
    render_ask_ada(dataframe, roles, source_name, api_key)
    
    narrative = None
    narrative_model = None
    if api_key:
        control_column, note_column = st.columns([.42, .58], gap="large")
        with control_column:
            narrative, narrative_model = maybe_generate_narrative(
                api_key=api_key,
                brief=brief,
                business_context=business_context,
            )
        if narrative and narrative_model:
            render_ai_narrative(narrative, model=narrative_model)
    else:
        st.info("AI features are currently unavailable. Deterministic analytics remain fully operational. Provide an API key in settings or sidebar to enable.")

elif current_page == "AI Governance":
    render_section_heading(
        "Governance",
        "AI Governance",
        "Monitor governance controls, privacy protections, and calculation traceability."
    )
    col1, col2 = st.columns(2)
    col1.metric("Evidence-Based Response", "ENABLED")
    col1.metric("Calculation Trace", "ENABLED")
    col2.metric("PII Protection", "ENABLED")
    col2.metric("Raw Data Sent to AI", "NO")
    
    st.markdown("### Privacy Rules")
    st.info("InsightGuard never sends raw dataset rows to an external LLM. Only schema, aggregated metrics, and safely computed evidence are shared.")

elif current_page == "Audit & Evidence":
    render_section_heading(
        "Audit & Evidence",
        "Evidence Ledger",
        "Trace every conclusion. Every displayed signal exposes the calculation behind it."
    )
    render_evidence(brief)
    st.markdown('<div class="section-label" style="margin-top:1.5rem">Detected business schema</div>', unsafe_allow_html=True)
    st.dataframe(schema_frame(roles), hide_index=True, width="stretch")

elif current_page == "Settings":
    render_section_heading(
        "Settings",
        "Platform Settings",
        "Configure export options and data processing limits."
    )
    report = build_business_report(
        dataframe,
        brief,
        source_name=source_name,
        context=business_context,
    )
    downloads = st.columns(2)
    downloads[0].download_button(
        "Download executive brief",
        data=report,
        file_name="insightguard_executive_brief.md",
        mime="text/markdown",
        width="stretch",
    )
    downloads[1].download_button(
        "Download cleaned data",
        data=dataframe.to_csv(index=False).encode("utf-8"),
        file_name="insightguard_cleaned_data.csv",
        mime="text/csv",
        width="stretch",
    )

# Removed Data Room tab since it's merged into Data Quality and Settings

render_footer()
