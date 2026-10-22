# InsightGuard Analytics: Enterprise Data Analytics & AI Governance

[![License: MIT](https://img.shields.io/badge/License-MIT-20a779.svg)](LICENSE)
[![Streamlit](https://img.shields.io/badge/Streamlit-live_product-ff4b4b?logo=streamlit&logoColor=white)](https://streamlit.io/)

**InsightGuard Analytics** is a professional enterprise analytics platform that transforms operational data into governed analytics, data-quality insights, anomaly detection, forecasting, and evidence-backed AI recommendations.

---

## 1. Project Overview
InsightGuard Analytics is a privacy-conscious, locally executing data analyst tool built with Python, Streamlit, pandas, and Plotly. It allows business users to upload CSV or Excel files and instantly receive an executive dashboard, complete with data quality metrics, anomaly detection, guarded forecasts, and an AI-assisted narrative that requires no manual BI configuration.

## 2. Business Problem
Modern enterprises generate vast amounts of spreadsheet data, but extracting actionable insights typically requires time-consuming dashboard development, manual data cleaning, or sending sensitive data to external AI tools which poses significant data privacy and governance risks.

## 3. Solution
InsightGuard bridges this gap by providing an automated, deterministic analytical engine that runs locally on your machine. It generates clear visualizations and calculated evidence while offering an optional AI-assisted governance layer that only processes aggregated metadata—never raw rows.

## 4. Architecture
The application is built on a Streamlit frontend with a modular Python backend:
- `app.py`: Streamlit orchestration and sidebar navigation logic (Customized for InsightGuard).
- `ui.py`: Presentation components and Plotly styling (Customized with Enterprise UI).
- `business_insights.py` & `ai_insights.py`: Core logic for interpreting deterministic calculations.
- `aggregation.py`, `timeseries.py`, `anomalies.py`, `forecasting.py`: The analytical workhorses that handle period calculations and time-series projections.

## 5. Data Flow
1. **Upload:** User drops a CSV/Excel file.
2. **Clean & Infer:** `pipeline.py` sanitizes data and detects types.
3. **Detect Roles:** `schema.py` identifies metric, date, segment, and identifier columns.
4. **Calculate:** Engine calculates evidence, data quality, anomalies, and forecasts.
5. **Dashboard:** Streamlit renders an interactive, page-based UI.
6. **Optional AI:** If configured, safe schema/metadata is sent for query planning and strategic reads.

## 6. Analytics Capabilities
- **Automated KPI Generation:** Computes period-over-period trends and category breakdowns.
- **Natural Language Querying (Ask InsightGuard):** Translates questions into local pandas calculations.
- **Drill-down Focus:** Regroup analysis by focusing on a single dimension slice.
- **Movement Waterfall:** Reconciles the latest metric changes by segment.

## 7. Data Quality
InsightGuard automatically monitors completeness, uniqueness, and consistency. The platform exposes missing cells, duplicate records, and invalid values in a transparent Data Quality dashboard and cleaning audit.

## 8. AI Governance
A dedicated AI Governance dashboard monitors active privacy controls:
- **Evidence-Based Response:** Enabled
- **Calculation Traceability:** Enabled
- **PII Protection:** Enabled (never sending raw records to AI)

## 9. Privacy Model
InsightGuard works entirely without an API key for its deterministic capabilities. When an OpenAI API key is supplied, **raw rows and cell values are never sent to the model**. The AI only receives the table schema, aggregated metadata, and calculated evidence.

## 10. Forecasting
Provides a guarded baseline forecast using historical trends. The time-series forecasting engine accounts for seasonality and presents a backtest to show historical accuracy.

## 11. Anomaly Detection
An automated anomaly radar identifies periods outside a robust trendline band. These deviations are flagged in the UI, detailed in the Anomalies dashboard, and fed into the AI evidence ledger.

## 12. Technology Stack
- **Frontend:** Streamlit
- **Data Engine:** Pandas, NumPy
- **Visualizations:** Plotly
- **AI Integration:** OpenAI Responses API (Optional)
- **Language:** Python 3.11+

## 13. Local Setup
```bash
# Setup virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
python -m pip install -r requirements.txt

# Run the application
streamlit run app.py
```

## 14. Configuration
No secrets are required for core operations. To enable the optional AI strategy layer, set the `OPENAI_API_KEY` in your environment variables, `.streamlit/secrets.toml`, or via the in-app sidebar.

## 15. Testing
The platform includes a comprehensive test suite.
```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

## 16. Security
Do not commit `.streamlit/secrets.toml` or any `.env` files containing API keys. The application adheres to strict data privacy principles by never sending raw dataset payloads over the network.

## 17. Limitations
- **File Size:** Limited to 25 MB by default for predictable performance.
- **Analysis Limit:** Analyzes the first 250,000 rows.
- **Deterministic Scope:** The AI query planner cannot answer questions that require row-level scanning if the deterministic engine lacks the capability.

## 18. Future Enhancements
- Expanded Data Quality metrics (outlier detection, PII flagging).
- Custom thresholding for Anomaly Detection in the UI.
- Support for direct SQL Database connections.

## 19. Licensing
This software is provided as a proprietary enterprise solution under the terms specified in the included [LICENSE](LICENSE) file.
