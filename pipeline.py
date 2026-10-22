"""Application-level orchestration for preparing an ADA analysis."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from analysis import CleaningReport, clean_dataframe
from business_insights import BusinessBrief, analyze_business
from schema import ColumnRoles, detect_roles


@dataclass(frozen=True)
class PreparedAnalysis:
    dataframe: pd.DataFrame
    cleaning_report: CleaningReport
    detected_roles: ColumnRoles
    truncated_rows: int

    def analyze(self, roles: ColumnRoles | None = None) -> BusinessBrief:
        return analyze_business(self.dataframe, roles or self.detected_roles)


def prepare_analysis(raw_dataframe: pd.DataFrame, *, row_limit: int) -> PreparedAnalysis:
    """Bound work, clean data, and detect its likely business schema."""
    original_rows = len(raw_dataframe)
    bounded = raw_dataframe.head(row_limit).copy() if original_rows > row_limit else raw_dataframe
    dataframe, cleaning_report = clean_dataframe(bounded)
    
    # Derive Revenue if possible and missing
    cols = {c.lower(): c for c in dataframe.columns}
    has_revenue = any(c in ["revenue", "sales", "amount", "total sales"] for c in cols)
    
    from dataclasses import replace
    if not has_revenue and "quantity" in cols and "unitprice" in cols:
        q_col = cols["quantity"]
        p_col = cols["unitprice"]
        
        # Calculate revenue, handling missing and invalid
        q_series = pd.to_numeric(dataframe[q_col], errors='coerce')
        p_series = pd.to_numeric(dataframe[p_col], errors='coerce')
        
        dataframe["Revenue"] = q_series * p_series
        
        # Calculate invalid tracking metrics
        cleaning_report = replace(
            cleaning_report,
            revenue_calculated=True,
            missing_quantity=int(dataframe[q_col].isna().sum()),
            missing_unitprice=int(dataframe[p_col].isna().sum()),
            invalid_quantity=int(q_series.isna().sum() - dataframe[q_col].isna().sum()),
            invalid_unitprice=int(p_series.isna().sum() - dataframe[p_col].isna().sum()),
            revenue_failures=int(dataframe["Revenue"].isna().sum())
        )
    else:
        cleaning_report = replace(cleaning_report, revenue_calculated=False)

    return PreparedAnalysis(
        dataframe=dataframe,
        cleaning_report=cleaning_report,
        detected_roles=detect_roles(dataframe),
        truncated_rows=max(original_rows - row_limit, 0),
    )


def apply_role_selection(
    detected: ColumnRoles,
    *,
    date: str,
    measure: str,
    dimension: str,
) -> ColumnRoles:
    return ColumnRoles(
        date=None if date == "None" else date,
        measure=None if measure == "None" else measure,
        dimension=None if dimension == "None" else dimension,
        identifier=detected.identifier,
        numeric=detected.numeric,
        dimensions=detected.dimensions,
    )


def focus_options(dataframe: pd.DataFrame, roles: ColumnRoles, limit: int = 40) -> list[str]:
    """Values of the active segment, most common first, for drill-down."""
    if not roles.dimension or roles.dimension not in dataframe.columns:
        return []
    counts = dataframe[roles.dimension].value_counts(dropna=True)
    return [str(value) for value in counts.head(limit).index]


def apply_focus(
    dataframe: pd.DataFrame,
    roles: ColumnRoles,
    focus: str | None,
) -> tuple[pd.DataFrame, ColumnRoles]:
    """Drill into one segment value and regroup by the next useful dimension."""
    if not focus or not roles.dimension:
        return dataframe, roles
    filtered = dataframe[dataframe[roles.dimension].astype(str) == focus]
    if filtered.empty:
        return dataframe, roles
    replacement = next(
        (
            column
            for column in roles.dimensions
            if column != roles.dimension
            and column in filtered.columns
            and filtered[column].nunique(dropna=True) >= 2
        ),
        None,
    )
    focused_roles = ColumnRoles(
        date=roles.date,
        measure=roles.measure,
        dimension=replacement,
        identifier=roles.identifier,
        numeric=roles.numeric,
        dimensions=roles.dimensions,
    )
    return filtered.reset_index(drop=True), focused_roles


def cleaning_audit_frame(report: CleaningReport) -> pd.DataFrame:
    rows = [
        ["Empty rows removed", report.empty_rows_removed],
        ["Empty columns removed", report.empty_columns_removed],
        ["Exported index columns removed", report.index_columns_removed],
        ["Duplicate rows removed", report.duplicate_rows_removed],
        ["Numeric columns inferred", report.numeric_columns_inferred],
        ["Datetime columns inferred", report.datetime_columns_inferred],
    ]
    if getattr(report, "revenue_calculated", False):
        rows.extend([
            ["Missing Quantity values", getattr(report, "missing_quantity", 0)],
            ["Missing UnitPrice values", getattr(report, "missing_unitprice", 0)],
            ["Invalid Quantity values", getattr(report, "invalid_quantity", 0)],
            ["Invalid UnitPrice values", getattr(report, "invalid_unitprice", 0)],
            ["Rows where Revenue could not be calculated", getattr(report, "revenue_failures", 0)],
        ])
    return pd.DataFrame(rows, columns=["Operation", "Count"])


def schema_frame(roles: ColumnRoles) -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["Primary metric", roles.measure or "Not detected"],
            ["Business segment", roles.dimension or "Not detected"],
            ["Date", roles.date or "Not detected"],
            ["Identifier", roles.identifier or "Not detected"],
        ],
        columns=["Role", "Column"],
    )
