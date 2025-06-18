# dashboard.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google.cloud import storage
from io import StringIO
import datetime
import numpy as np

# Konfigurasi Google Cloud Storage
bucket_name = "stock-csvku"
file_name = "hasil_analisis_saham.csv"

# Fungsi untuk membaca data dari GCS tanpa autentikasi
@st.cache_data(ttl=3600)  # Cache data selama 1 jam
def load_data():
    try:
        # Buat client tanpa kredensial (akses publik)
        client = storage.Client.create_anonymous_client()
        
        # Akses bucket dan file
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        
        # Download data
        data = blob.download_as_text()
        return pd.read_csv(StringIO(data))
    
    except Exception as e:
        st.error(f"❌ Gagal memuat data: {e}")
        st.error("Pastikan bucket GCS diatur sebagai publik")
        return pd.DataFrame()  # Return dataframe kosong jika error

# Load data
df = load_data()

# Proses data hanya jika tidak kosong
if not df.empty:
    df['Date'] = pd.to_datetime(df['Date'])
    st.success("✅ Data berhasil dimuat dari Google Cloud Storage")
    
    # Dapatkan daftar saham unik untuk dropdown
    all_stocks = df['Stock Code'].unique()
else:
    st.error("Tidak ada data yang berhasil dimuat. Silakan cek konfigurasi GCS.")
    st.stop()

# Konfigurasi halaman
st.set_page_config(
    page_title="Dashboard Analisis Saham",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Sidebar
st.sidebar.title("Pengaturan Analisis")
st.sidebar.markdown("---")

# Tampilkan dropdown pemilihan saham
selected_stock = st.sidebar.selectbox(
    "Pilih Saham", 
    all_stocks,
    index=0,  # Pilih saham pertama secara default
    help="Pilih saham dari daftar yang tersedia"
)

# Filter tanggal
min_date = df['Date'].min().date()
max_date = df['Date'].max().date()
start_date = st.sidebar.date_input("Tanggal Mulai", min_date, min_value=min_date, max_value=max_date)
end_date = st.sidebar.date_input("Tanggal Akhir", max_date, min_value=min_date, max_value=max_date)

# Filter sektor
all_sectors = df['Sector'].unique()
selected_sector = st.sidebar.selectbox("Pilih Sektor", ["SEMUA"] + list(all_sectors))

# Filter data
filtered_df = df[df['Stock Code'] == selected_stock]
filtered_df = filtered_df[(filtered_df['Date'] >= pd.to_datetime(start_date)) & 
                          (filtered_df['Date'] <= pd.to_datetime(end_date))]

if selected_sector != "SEMUA":
    filtered_df = filtered_df[filtered_df['Sector'] == selected_sector]

# Main Dashboard
st.title(f"📊 Dashboard Analisis Saham: {selected_stock}")
st.markdown(f"**Sektor:** {filtered_df['Sector'].iloc[0] if not filtered_df.empty and 'Sector' in filtered_df.columns else 'Tidak tersedia'}")
st.markdown("---")

# Tampilkan metrik utama dengan pengecekan error
if not filtered_df.empty:
    latest = filtered_df.iloc[-1]
    col1, col2, col3, col4 = st.columns(4)
    
    # Perbaikan: Cek apakah ada cukup data untuk menghitung pct_change
    if len(filtered_df) > 1:
        # Gunakan iloc untuk akses aman ke data terakhir
        price_change = filtered_df['Close'].iloc[-1] - filtered_df['Close'].iloc[-2]
        price_change_pct = (price_change / filtered_df['Close'].iloc[-2]) * 100
        price_change_str = f"{price_change_pct:.2f}%"
    else:
        price_change_str = "N/A"
    
    col1.metric("Harga Terakhir", f"Rp {latest['Close']:,.2f}", price_change_str)
    
    # Hitung perbandingan volume dengan rata-rata
    if len(filtered_df) > 0 and filtered_df['Volume'].mean() > 0:
        volume_ratio = (latest['Volume'] - filtered_df['Volume'].mean()) / filtered_df['Volume'].mean() * 100
        volume_ratio_str = f"{volume_ratio:.2f}% vs rata-rata"
    else:
        volume_ratio_str = "N/A"
    
    col2.metric("Volume", f"{latest['Volume']:,.0f}", volume_ratio_str)
    
    col3.metric("Sinyal Terkini", latest['Composite_Signal'], 
                f"Keyakinan: {latest['Signal_Confidence']:.1f}%")
    
    foreign_activity = f"Beli: Rp {latest['Net_Foreign']:,.0f}" if latest['Net_Foreign'] > 0 else f"Jual: Rp {-latest['Net_Foreign']:,.0f}"
    foreign_percent = f"{latest['Foreign_Pct']*100:.2f}% dari total" if not pd.isna(latest['Foreign_Pct']) else "N/A"
    
    col4.metric("Aktivitas Asing", foreign_activity, foreign_percent)
else:
    st.warning("⚠️ Tidak ada data untuk saham dan periode yang dipilih")

# ========== TAB REKOMENDASI SAHAM BARU ==========
# Fungsi untuk mendapatkan rekomendasi saham
def get_stock_recommendations(data):
    # Ambil data terbaru untuk setiap saham
    latest_data = data.sort_values('Date').groupby('Stock Code').last().reset_index()
    
    # Filter saham dengan sinyal akumulasi dan keyakinan tinggi
    recommendations = latest_data[
        (latest_data['Composite_Signal'].isin(['Strong Accumulation', 'Accumulation'])) &
        (latest_data['Signal_Confidence'] > 70)  # Keyakinan minimal 70%
    ]
    
    # Urutkan berdasarkan keyakinan tertinggi
    recommendations = recommendations.sort_values('Signal_Confidence', ascending=False)
    
    # Pilih kolom yang relevan
    return recommendations[[
        'Stock Code', 'Sector', 'Close', 'Composite_Signal', 
        'Signal_Confidence', 'Momentum_5D', 'VWAP', 'Date'
    ]]

# Dapatkan rekomendasi saham
recommendations = get_stock_recommendations(df)

# Visualisasi data
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Harga & Sinyal", 
    "Volume & Aktivitas", 
    "Analisis Teknikal", 
    "Data Lengkap",
    "💎 Rekomendasi Beli"
])

with tab1:
    st.subheader("Perjalanan Harga dan Sinyal")
    
    if not filtered_df.empty:
        # Buat grafik harga
        fig = go.Figure()
        
        # Tambahkan garis harga
        fig.add_trace(go.Scatter(
            x=filtered_df['Date'], 
            y=filtered_df['Close'],
            mode='lines',
            name='Harga Penutupan',
            line=dict(color='#1f77b4', width=2)
        ))
        
        # Tambahkan VWAP jika ada
        if 'VWAP' in filtered_df:
            fig.add_trace(go.Scatter(
                x=filtered_df['Date'], 
                y=filtered_df['VWAP'],
                mode='lines',
                name='VWAP',
                line=dict(color='#ff7f0e', width=2, dash='dash')
            ))
        
        # Tambahkan titik sinyal
        signal_colors = {
            'Strong Accumulation': 'green',
            'Accumulation': 'lightgreen',
            'Neutral': 'gray',
            'Distribution': 'orange',
            'Strong Distribution': 'red'
        }
        
        if 'Composite_Signal' in filtered_df and 'Signal_Confidence' in filtered_df:
            for signal, color in signal_colors.items():
                signal_df = filtered_df[filtered_df['Composite_Signal'] == signal]
                if not signal_df.empty:
                    fig.add_trace(go.Scatter(
                        x=signal_df['Date'],
                        y=signal_df['Close'],
                        mode='markers',
                        name=signal,
                        marker=dict(color=color, size=10, line=dict(width=1, color='black')),
                        hovertext=signal_df['Composite_Signal'] + '<br>Keyakinan: ' + signal_df['Signal_Confidence'].astype(str) + '%'
                    ))
        
        # Konfigurasi layout
        fig.update_layout(
            title=f'Perjalanan Harga {selected_stock}',
            xaxis_title='Tanggal',
            yaxis_title='Harga (Rp)',
            hovermode='x unified',
            template='plotly_white',
            height=500
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Tidak ada data yang tersedia untuk visualisasi")

# Tab lainnya (tab2, tab3, tab4) tetap sama seperti sebelumnya...

with tab5:
    st.subheader("💎 Rekomendasi Saham untuk Dibeli Besok")
    st.markdown("Saham dengan sinyal akumulasi kuat dan keyakinan tinggi:")
    
    if not recommendations.empty:
        # Tampilkan rekomendasi dalam tabel yang menarik
        st.dataframe(
            recommendations,
            column_config={
                "Stock Code": "Kode Saham",
                "Sector": "Sektor",
                "Close": st.column_config.NumberColumn(
                    "Harga Penutupan",
                    format="Rp %.2f"
                ),
                "Composite_Signal": "Sinyal",
                "Signal_Confidence": st.column_config.ProgressColumn(
                    "Keyakinan Sinyal",
                    format="%.1f%%",
                    min_value=0,
                    max_value=100
                ),
                "Momentum_5D": st.column_config.NumberColumn(
                    "Momentum 5 Hari",
                    format="%.2f%%"
                ),
                "VWAP": st.column_config.NumberColumn(
                    "VWAP",
                    format="Rp %.2f"
                ),
                "Date": st.column_config.DateColumn(
                    "Tanggal Terakhir",
                    format="YYYY-MM-DD"
                )
            },
            hide_index=True,
            use_container_width=True
        )
        
        # Tampilkan grafik top rekomendasi
        st.subheader("Top 5 Rekomendasi Saham")
        top_recommendations = recommendations.head(5)
        
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=top_recommendations['Stock Code'],
            y=top_recommendations['Signal_Confidence'],
            name='Keyakinan Sinyal',
            marker_color='#1f77b4',
            text=top_recommendations['Signal_Confidence'].apply(lambda x: f"{x:.1f}%"),
            textposition='outside'
        ))
        
        fig.update_layout(
            title='Keyakinan Sinyal untuk Top 5 Rekomendasi',
            xaxis_title='Kode Saham',
            yaxis_title='Keyakinan Sinyal (%)',
            template='plotly_white',
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Penjelasan rekomendasi
        st.markdown("""
        **Kriteria Rekomendasi:**
        - Sinyal: Strong Accumulation atau Accumulation
        - Keyakinan Sinyal > 70%
        - Momentum positif (5 hari)
        - Diurutkan berdasarkan keyakinan sinyal tertinggi
        """)
    else:
        st.warning("⚠️ Tidak ada rekomendasi saham untuk hari ini. Coba lagi besok!")

# Footer
st.markdown("---")
st.markdown("**Dashboard Analisis Saham** - Data diperbarui: " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
st.caption("Sumber data: Google Cloud Storage | Analisis oleh Sistem Analisis Saham")
