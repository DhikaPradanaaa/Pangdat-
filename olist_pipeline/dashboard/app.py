from __future__ import annotations

import os
from pathlib import Path

import mysql.connector
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

st.set_page_config(
    page_title="Olist Commerce Intelligence",
    page_icon="▦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
      --ink: #142033;
      --slate: #536176;
      --paper: #f5f7fa;
      --panel: #ffffff;
      --cobalt: #2558c7;
      --coral: #f06449;
      --mint: #32a887;
      --line: #dbe2ea;
    }
    .stApp { background: var(--paper); color: var(--ink); }
    h1, h2, h3 { font-family: Bahnschrift, "Arial Narrow", sans-serif; letter-spacing: -0.02em; color: var(--ink); }
    p, label, .stMarkdown { font-family: Aptos, "Segoe UI", sans-serif; }
    [data-testid="stSidebar"] { background: #162235; }
    [data-testid="stSidebar"] * { color: #edf3fb !important; }
    .manifest {
      background: var(--ink); color: white; padding: 22px 26px; border-radius: 4px;
      box-shadow: 0 12px 30px rgba(20,32,51,.12); margin-bottom: 18px;
    }
    .manifest-kicker { color: #9fb6da; font: 700 11px Consolas, monospace; letter-spacing: .14em; text-transform: uppercase; }
    .manifest-title { font: 700 30px Bahnschrift, sans-serif; margin: 5px 0 16px; }
    .pipeline-rail { display: grid; grid-template-columns: repeat(5,1fr); gap: 8px; }
    .pipeline-node { border-top: 3px solid var(--mint); padding-top: 7px; font: 700 11px Consolas, monospace; color: #dce8f8; }
    .metric-card { background: var(--panel); border: 1px solid var(--line); border-radius: 3px; padding: 17px 18px; min-height: 110px; }
    .metric-label { font: 700 10px Consolas, monospace; color: var(--slate); letter-spacing: .1em; text-transform: uppercase; }
    .metric-value { font: 700 27px Bahnschrift, sans-serif; color: var(--ink); margin-top: 7px; }
    .metric-note { font: 12px Aptos, sans-serif; color: var(--slate); margin-top: 3px; }
    .status-ok { color: #66d2b2; }
    div[data-testid="stPlotlyChart"] { background: white; border: 1px solid var(--line); padding: 8px; }
    .block-container { padding-top: 1.4rem; padding-bottom: 3rem; }
    @media (max-width: 800px) { .pipeline-rail { grid-template-columns: 1fr; } }
    </style>
    """,
    unsafe_allow_html=True,
)


def connection(database: str, dashboard: bool = True):
    user = os.getenv("DASHBOARD_USER", "olist_dashboard") if dashboard else os.getenv("MYSQL_USER", "root")
    password = os.getenv("DASHBOARD_PASSWORD", "olist_dashboard_local") if dashboard else os.getenv("MYSQL_PASSWORD", "")
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
    )


@st.cache_data(ttl=300)
def query(sql: str, database: str = "olist_dwh") -> pd.DataFrame:
    conn = connection(database)
    try:
        return pd.read_sql(sql, conn)
    finally:
        conn.close()


def metric_card(label: str, value: str, note: str = "") -> None:
    st.markdown(
        f'<div class="metric-card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div><div class="metric-note">{note}</div></div>',
        unsafe_allow_html=True,
    )


latest = query(
    """
    SELECT batch_id,business_date,completed_at,status,source_rows,clean_rows,rejected_rows
    FROM etl_batch ORDER BY started_at DESC LIMIT 1
    """,
    database="olist_staging",
)
latest_row = latest.iloc[0] if not latest.empty else None
status = latest_row["status"] if latest_row is not None else "BELUM ADA BATCH"
updated = str(latest_row["completed_at"]) if latest_row is not None else "-"

st.markdown(
    f"""
    <div class="manifest">
      <div class="manifest-kicker">Commerce data manifest · batch status <span class="status-ok">{status}</span></div>
      <div class="manifest-title">Olist Commerce Intelligence</div>
      <div class="pipeline-rail">
        <div class="pipeline-node">01 · OLTP</div>
        <div class="pipeline-node">02 · RAW STAGING</div>
        <div class="pipeline-node">03 · DATA QUALITY</div>
        <div class="pipeline-node">04 · WAREHOUSE</div>
        <div class="pipeline-node">05 · MART</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.sidebar.markdown("## Kendali laporan")
page = st.sidebar.radio(
    "Pilih tampilan",
    ["Ringkasan", "Penjualan", "Fulfillment", "Customer experience", "Data quality"],
)
st.sidebar.caption(f"Batch terakhir: {updated}")
if st.sidebar.button("Muat ulang data"):
    st.cache_data.clear()
    st.rerun()


if page == "Ringkasan":
    kpis = query(
        """
        SELECT
          (SELECT COUNT(*) FROM fact_order) AS orders,
          (SELECT ROUND(SUM(line_total),2) FROM fact_sales) AS gross_sales,
          (SELECT ROUND(SUM(line_total)/COUNT(DISTINCT order_key),2) FROM fact_sales) AS avg_order_value,
          (SELECT ROUND(100*SUM(is_late)/NULLIF(SUM(is_delivered),0),2) FROM fact_order) AS late_percent,
          (SELECT ROUND(AVG(review_score),2) FROM fact_review) AS avg_review
        """
    ).iloc[0]
    columns = st.columns(5)
    values = [
        ("Pesanan", f"{int(kpis['orders']):,}", "grain satu order"),
        ("Gross sales", f"R$ {kpis['gross_sales']:,.2f}", "produk + freight"),
        ("Average order", f"R$ {kpis['avg_order_value']:,.2f}", "per pesanan"),
        ("Terlambat", f"{kpis['late_percent']:.2f}%", "dari order delivered"),
        ("Skor ulasan", f"{kpis['avg_review']:.2f}", "skala 1–5"),
    ]
    for column, item in zip(columns, values):
        with column:
            metric_card(*item)

    monthly = query("SELECT * FROM mart_monthly_sales ORDER BY year_number,month_number")
    monthly["period"] = pd.to_datetime(monthly.assign(day=1)[["year_number", "month_number", "day"]].rename(columns={"year_number":"year","month_number":"month"}))
    figure = px.area(monthly, x="period", y="gross_sales", markers=True, color_discrete_sequence=["#2558c7"])
    figure.update_layout(title="Arus penjualan bulanan", xaxis_title=None, yaxis_title="Gross sales (R$)", plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(figure, use_container_width=True)

elif page == "Penjualan":
    st.header("Penjualan dan kategori")
    monthly = query("SELECT * FROM mart_monthly_sales ORDER BY year_number,month_number")
    category = query("SELECT * FROM mart_category_performance ORDER BY gross_sales DESC LIMIT 15")
    col1, col2 = st.columns([1.4, 1])
    with col1:
        monthly["period"] = monthly["year_number"].astype(str) + "-" + monthly["month_number"].astype(str).str.zfill(2)
        fig = px.bar(monthly, x="period", y="gross_sales", color_discrete_sequence=["#2558c7"])
        fig.update_layout(title="Gross sales per bulan", xaxis_title=None, yaxis_title="R$", plot_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = px.bar(category.sort_values("gross_sales"), x="gross_sales", y="category_name_english", orientation="h", color_discrete_sequence=["#f06449"])
        fig.update_layout(title="15 kategori teratas", xaxis_title="R$", yaxis_title=None, plot_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)
    st.dataframe(category, use_container_width=True, hide_index=True)

elif page == "Fulfillment":
    st.header("Fulfillment dan ketepatan pengiriman")
    delivery = query("SELECT * FROM mart_delivery_performance ORDER BY year_number,month_number")
    delivery["period"] = delivery["year_number"].astype(str) + "-" + delivery["month_number"].astype(str).str.zfill(2)
    col1, col2 = st.columns(2)
    with col1:
        fig = px.line(delivery, x="period", y="late_percent", markers=True, color_discrete_sequence=["#f06449"])
        fig.update_layout(title="Persentase keterlambatan", xaxis_title=None, yaxis_title="%", plot_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = px.line(delivery, x="period", y="avg_delivery_days", markers=True, color_discrete_sequence=["#32a887"])
        fig.update_layout(title="Rata-rata hari pengiriman", xaxis_title=None, yaxis_title="Hari", plot_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)
    st.dataframe(delivery, use_container_width=True, hide_index=True)

elif page == "Customer experience":
    st.header("Customer experience")
    experience = query("SELECT * FROM mart_customer_experience ORDER BY is_late")
    scores = query("SELECT review_score,COUNT(*) AS review_count FROM fact_review GROUP BY review_score ORDER BY review_score")
    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(scores, x="review_score", y="review_count", color_discrete_sequence=["#2558c7"])
        fig.update_layout(title="Distribusi skor ulasan", xaxis_title="Skor", yaxis_title="Jumlah", plot_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        experience["delivery_status"] = experience["is_late"].map({0:"Tepat waktu",1:"Terlambat"})
        fig = px.bar(experience, x="delivery_status", y="average_review_score", color="delivery_status", color_discrete_map={"Tepat waktu":"#32a887","Terlambat":"#f06449"})
        fig.update_layout(title="Skor dan keterlambatan", xaxis_title=None, yaxis_title="Rata-rata skor", showlegend=False, plot_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)

else:
    st.header("Kualitas dan kesehatan pipeline")
    batches = query("SELECT * FROM mart_data_quality ORDER BY completed_at DESC LIMIT 20")
    rules = query(
        """
        SELECT rule_id,dimension_name,severity,detected_count,corrected_count,open_count,quarantined_count,result
        FROM dq_rule_result
        WHERE batch_id=(SELECT batch_id FROM etl_batch ORDER BY started_at DESC LIMIT 1)
        ORDER BY detected_count DESC
        """,
        database="olist_staging",
    )
    if latest_row is not None:
        cols = st.columns(3)
        with cols[0]: metric_card("Extracted", f"{int(latest_row['source_rows']):,}", "baris perubahan batch")
        with cols[1]: metric_card("Clean snapshot", f"{int(latest_row['clean_rows']):,}", "seluruh tabel clean")
        with cols[2]: metric_card("Quarantine", f"{int(latest_row['rejected_rows']):,}", "issue berseverity error")
    st.subheader("Riwayat batch")
    st.dataframe(batches, use_container_width=True, hide_index=True)
    st.subheader("Hasil aturan kualitas terbaru")
    st.dataframe(rules, use_container_width=True, hide_index=True)
