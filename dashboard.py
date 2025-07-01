# POWERFUL STREAMLIT DASHBOARD: MONEY FLOW, VOLUME, FOREIGN INFLOW

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# Konfigurasi halaman
st.set_page_config(page_title="📊 Smart Money Flow Dashboard", layout="wide")
st.title("💰 Dashboard Analisa Smart Money & Top Picks")

CSV_URL = "https://storage.googleapis.com/stock-csvku/hasil_gabungan.csv"

@st.cache_data(ttl=3600)
def load_data():
    df = pd.read_csv(CSV_URL)
    df['Last Trading Date'] = pd.to_datetime(df['Last Trading Date'])
    num_cols = ["Volume", "Close", "VWAP", "Foreign Buy", "Foreign Sell", "Money Flow", "MFI14"]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df

df = load_data()

# Kolom tambahan
st.sidebar.header("📅 Ringkasan Harian")
latest_date = df["Last Trading Date"].max()
st.sidebar.metric("Total Volume", f"{df[df['Last Trading Date'] == latest_date]['Volume'].sum():,.0f}")
st.sidebar.metric("Saham Naik", (df[(df['Last Trading Date'] == latest_date) & (df['Change'] > 0)].shape[0]))
st.sidebar.metric("Saham Turun", (df[(df['Last Trading Date'] == latest_date) & (df['Change'] < 0)].shape[0]))

if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.experimental_rerun()

# Kolom tambahan lanjutan

df.sort_values(by=["Stock Code", "Last Trading Date"], inplace=True)
df["Avg Volume 5D"] = df.groupby("Stock Code")["Volume"].transform(lambda x: x.rolling(5).mean())

# Week + perubahan mingguan volume
if "Week" not in df.columns:
    df["Week"] = df["Last Trading Date"].dt.strftime("%Y-%U")
weekly = df.groupby(["Stock Code", "Week"])["Volume"].sum().reset_index()
weekly["Prev Volume"] = weekly.groupby("Stock Code")["Volume"].shift(1)
weekly["Volume Change Positive"] = (weekly["Volume"] > weekly["Prev Volume"]).astype(int)
latest_week = df.groupby("Stock Code")["Week"].last().reset_index().rename(columns={"Week": "Latest Week"})
weekly = weekly.merge(latest_week, on="Stock Code")
weekly = weekly[weekly["Week"] == weekly["Latest Week"]][["Stock Code", "Volume Change Positive"]]
df = df.merge(weekly, on="Stock Code", how="left")

# Scoring logika

def calc_score(df):
    df = df.copy()
    df["Score"] = 0
    df["Score"] += (df["Final Signal"].str.contains("Akumulasi")).astype(int) * 2
    df["Score"] += (df["Foreign Flow"] == "Inflow") * 2
    df["Score"] += ((df["Volume"] / df["Avg Volume 5D"]) > 1.5).astype(int) * 2
    df["Score"] += (df["Close"] >= df["VWAP"]).astype(int)
    df["Score"] += df["Volume Change Positive"].fillna(0).astype(int)
    df["Score"] += df["Unusual Volume"].astype(int)
    df["Score"] += (df["MFI14"] > 70).astype(int)  # momentum tinggi
    return df

scored_df = calc_score(df)
latest_df = scored_df[scored_df["Last Trading Date"] == latest_date]
top20 = latest_df.sort_values(by="Score", ascending=False).drop_duplicates("Stock Code").head(20)
alerts = latest_df[(latest_df["Unusual Volume"] == 1) & (latest_df["Foreign Flow"] == "Inflow")]

# Tabs
st.markdown("### 📌 Navigasi")
tab1, tab2, tab3 = st.tabs(["🏆 Top Picks", "📊 Grafik Volume & Harga", "📈 Money Flow per Saham"])

with tab1:
    st.subheader("🏆 20 Saham Skor Tertinggi Hari Ini")
    st.dataframe(top20[["Stock Code", "Company Name", "Close", "VWAP", "Volume", "Score", "Final Signal", "Foreign Flow"]].sort_values(by="Score", ascending=False))
    csv = top20.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download Top Picks", data=csv, file_name="top_picks.csv")

    if not alerts.empty:
        st.warning("🚨 Alert: Unusual Volume + Foreign Inflow Detected!")
        st.dataframe(alerts[["Stock Code", "Company Name", "Final Signal", "Score"]])

with tab2:
    st.subheader("📊 Volume & Harga")
    stock = st.selectbox("Pilih Saham", df["Stock Code"].unique())
    range_date = st.date_input("Rentang Tanggal", [df["Last Trading Date"].min(), df["Last Trading Date"].max()])
    temp = df[(df["Stock Code"] == stock) & (df["Last Trading Date"] >= pd.to_datetime(range_date[0])) & (df["Last Trading Date"] <= pd.to_datetime(range_date[1]))].copy()
    temp["Non Foreign"] = temp["Volume"] - temp["Foreign Buy"]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=temp["Last Trading Date"], y=temp["Foreign Buy"], name="Foreign Buy", marker_color="green"))
    fig.add_trace(go.Bar(x=temp["Last Trading Date"], y=temp["Foreign Sell"], name="Foreign Sell", marker_color="red"))
    fig.add_trace(go.Bar(x=temp["Last Trading Date"], y=temp["Non Foreign"], name="Non Foreign", marker_color="royalblue"))
    fig.add_trace(go.Scatter(x=temp["Last Trading Date"], y=temp["Close"], name="Close", yaxis="y2", mode="lines+markers", line=dict(color="black")))

    fig.update_layout(
        barmode="stack",
        yaxis=dict(title="Volume"),
        yaxis2=dict(title="Close Price", overlaying="y", side="right"),
        title=f"Volume vs Harga - {stock}",
        height=550
    )
    st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.subheader("📈 Money Flow Detail & MFI")
    pick = st.selectbox("Pilih Saham", df["Stock Code"].unique())
    stock_df = df[df["Stock Code"] == pick].sort_values("Last Trading Date")

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=stock_df["Last Trading Date"], y=stock_df["Money Flow"], name="Money Flow", line=dict(color="green")))
    fig2.add_trace(go.Scatter(x=stock_df["Last Trading Date"], y=stock_df["Volume"], name="Volume", line=dict(color="blue")))
    fig2.update_layout(title=f"Money Flow & Volume - {pick}", height=450)
    st.plotly_chart(fig2, use_container_width=True)

    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(x=stock_df["Last Trading Date"], y=stock_df["MFI14"], name="MFI14", line=dict(color="orange")))
    fig3.add_trace(go.Scatter(x=stock_df["Last Trading Date"], y=stock_df["Close"], name="Close", line=dict(color="black")))
    fig3.update_layout(title=f"MFI vs Harga - {pick}", height=450)
    st.plotly_chart(fig3, use_container_width=True)
