# streamlit_app.py
import streamlit as st
import pandas as pd
import plotly.express as px

# Load data dari hasil_gabungan.csv
@st.cache_data
def load_data():
    return pd.read_csv("hasil_gabungan.csv", parse_dates=["Last Trading Date"])

df = load_data()

st.set_page_config(page_title="📊 Money Flow Dashboard", layout="wide")
st.title("📈 Money Flow & Smart Money Tracker")

# Sidebar: Filter global
with st.sidebar:
    st.header("🔎 Filter")
    selected_date = st.date_input("Tanggal", df["Last Trading Date"].max().date())
    sectors = st.multiselect("Pilih Sektor", sorted(df["Sector"].dropna().unique()), default=None)
    sort_by = st.selectbox("Urutkan Berdasarkan", ["MFI14", "Volume", "Money Flow"], index=0)

# Filter data
filtered_df = df[df["Last Trading Date"] == pd.to_datetime(selected_date)]
if sectors:
    filtered_df = filtered_df[filtered_df["Sector"].isin(sectors)]

# --- Top Money Flow Section ---
st.subheader("🚀 Top Saham Berdasarkan Money Flow")
col1, col2 = st.columns([3, 1])
with col1:
    st.dataframe(filtered_df.sort_values(by=sort_by, ascending=False).head(15), use_container_width=True)
with col2:
    top_chart = px.bar(filtered_df.sort_values(by=sort_by, ascending=False).head(10), 
                       x="Stock Code", y=sort_by, color="Sector",
                       title=f"Top 10 Saham berdasarkan {sort_by}")
    st.plotly_chart(top_chart, use_container_width=True)

# --- Analisis Per Saham ---
st.subheader("🔍 Analisa Per Saham")
stocks = sorted(df["Stock Code"].dropna().unique())
selected_stock = st.selectbox("Pilih Kode Saham", stocks, index=stocks.index("TLKM") if "TLKM" in stocks else 0)

saham_df = df[df["Stock Code"] == selected_stock].sort_values("Last Trading Date")

colA, colB, colC = st.columns(3)
with colA:
    st.metric("💸 MFI Hari Ini", f'{saham_df.iloc[-1]["MFI14"]} ({saham_df.iloc[-1]["MFI Signal"]})')
with colB:
    st.metric("📥 Foreign Flow", saham_df.iloc[-1]["Foreign Flow"])
with colC:
    st.metric("📊 Final Signal", saham_df.iloc[-1]["Final Signal"])

st.markdown("### Trend Money Flow & Volume")
fig = px.line(saham_df, x="Last Trading Date", y=["Money Flow", "Volume"], markers=True)
fig.update_layout(yaxis_title="Jumlah")
st.plotly_chart(fig, use_container_width=True)

st.markdown("### MFI vs Harga")
fig2 = px.line(saham_df, x="Last Trading Date", y=["MFI14", "Close"], markers=True)
fig2.update_layout(yaxis_title="MFI / Harga")
st.plotly_chart(fig2, use_container_width=True)

st.markdown("---")
st.caption("Made with ❤️ using Streamlit + Plotly • v1")
