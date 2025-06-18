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
else:
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

# Pilih saham
all_stocks = df['Stock Code'].unique()
selected_stock = st.sidebar.selectbox("Pilih Saham", all_stocks)

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
st.markdown(f"**Sektor:** {filtered_df['Sector'].iloc[0] if not filtered_df.empty else 'Tidak tersedia'}")
st.markdown("---")

# Tampilkan metrik utama
if not filtered_df.empty:
    latest = filtered_df.iloc[-1]
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("Harga Terakhir", f"Rp {latest['Close']:,.2f}", 
                f"{filtered_df['Close'].pct_change()[-1]*100:.2f}%" if len(filtered_df) > 1 else "N/A")
    
    col2.metric("Volume", f"{latest['Volume']:,.0f}", 
                f"{(latest['Volume'] - filtered_df['Volume'].mean())/filtered_df['Volume'].mean()*100:.2f}% vs rata-rata" 
                if filtered_df['Volume'].mean() > 0 else "N/A")
    
    col3.metric("Sinyal Terkini", latest['Composite_Signal'], 
                f"Keyakinan: {latest['Signal_Confidence']:.1f}%")
    
    col4.metric("Aktivitas Asing", 
                f"Beli: Rp {latest['Net_Foreign']:,.0f}" if latest['Net_Foreign'] > 0 else f"Jual: Rp {-latest['Net_Foreign']:,.0f}", 
                f"{latest['Foreign_Pct']*100:.2f}% dari total")

# Visualisasi data
tab1, tab2, tab3, tab4 = st.tabs(["Harga & Sinyal", "Volume & Aktivitas", "Analisis Teknikal", "Data Lengkap"])

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
        
        # Tambahkan VWAP
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
        st.warning("Tidak ada data yang tersedia untuk filter yang dipilih")

with tab2:
    st.subheader("Volume dan Aktivitas Perdagangan")
    
    if not filtered_df.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            # Grafik Volume
            fig_vol = go.Figure()
            
            fig_vol.add_trace(go.Bar(
                x=filtered_df['Date'],
                y=filtered_df['Volume'],
                name='Volume',
                marker_color='#1f77b4'
            ))
            
            if 'Volume_MA_20' in filtered_df:
                fig_vol.add_trace(go.Scatter(
                    x=filtered_df['Date'],
                    y=filtered_df['Volume_MA_20'],
                    name='MA 20 Hari',
                    line=dict(color='#ff7f0e', width=2)
                ))
            
            fig_vol.update_layout(
                title='Volume Perdagangan',
                xaxis_title='Tanggal',
                yaxis_title='Volume',
                template='plotly_white',
                height=400
            )
            
            st.plotly_chart(fig_vol, use_container_width=True)
        
        with col2:
            # Grafik Aktivitas Asing
            fig_foreign = go.Figure()
            
            fig_foreign.add_trace(go.Bar(
                x=filtered_df['Date'],
                y=np.where(filtered_df['Net_Foreign'] > 0, filtered_df['Net_Foreign'], 0),
                name='Net Buy',
                marker_color='green'
            ))
            
            fig_foreign.add_trace(go.Bar(
                x=filtered_df['Date'],
                y=np.where(filtered_df['Net_Foreign'] < 0, filtered_df['Net_Foreign'], 0),
                name='Net Sell',
                marker_color='red'
            ))
            
            fig_foreign.update_layout(
                title='Aktivitas Investor Asing',
                xaxis_title='Tanggal',
                yaxis_title='Net Foreign (Rp)',
                barmode='relative',
                template='plotly_white',
                height=400
            )
            
            st.plotly_chart(fig_foreign, use_container_width=True)
    else:
        st.warning("Tidak ada data yang tersedia untuk filter yang dipilih")

with tab3:
    st.subheader("Analisis Teknikal Lanjutan")
    
    if not filtered_df.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            # Grafik Momentum
            if 'Momentum_5D' in filtered_df and 'Momentum_20D' in filtered_df:
                fig_momentum = go.Figure()
                
                fig_momentum.add_trace(go.Scatter(
                    x=filtered_df['Date'],
                    y=filtered_df['Momentum_5D'],
                    name='Momentum 5 Hari',
                    line=dict(color='#1f77b4', width=2)
                ))
                
                fig_momentum.add_trace(go.Scatter(
                    x=filtered_df['Date'],
                    y=filtered_df['Momentum_20D'],
                    name='Momentum 20 Hari',
                    line=dict(color='#ff7f0e', width=2)
                ))
                
                fig_momentum.add_hline(y=0, line_dash="dash", line_color="gray")
                fig_momentum.update_layout(
                    title='Momentum Harga',
                    xaxis_title='Tanggal',
                    yaxis_title='Momentum',
                    template='plotly_white',
                    height=400
                )
                
                st.plotly_chart(fig_momentum, use_container_width=True)
        
        with col2:
            # Grafik Relative Strength
            if 'RS' in filtered_df and 'RS_MA_10' in filtered_df:
                fig_rs = go.Figure()
                
                fig_rs.add_trace(go.Scatter(
                    x=filtered_df['Date'],
                    y=filtered_df['RS'],
                    name='Relative Strength',
                    line=dict(color='#1f77b4', width=2)
                ))
                
                fig_rs.add_trace(go.Scatter(
                    x=filtered_df['Date'],
                    y=filtered_df['RS_MA_10'],
                    name='RS MA 10 Hari',
                    line=dict(color='#ff7f0e', width=2)
                ))
                
                fig_rs.update_layout(
                    title='Kekuatan Relatif vs Pasar',
                    xaxis_title='Tanggal',
                    yaxis_title='Relative Strength',
                    template='plotly_white',
                    height=400
                )
                
                st.plotly_chart(fig_rs, use_container_width=True)
    else:
        st.warning("Tidak ada data yang tersedia untuk filter yang dipilih")

with tab4:
    st.subheader("Data Lengkap")
    
    if not filtered_df.empty:
        # Tampilkan data dalam bentuk tabel
        st.dataframe(
            filtered_df.sort_values('Date', ascending=False),
            hide_index=True,
            height=500,
            use_container_width=True
        )
        
        # Tombol download
        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Data sebagai CSV",
            data=csv,
            file_name=f"analisis_saham_{selected_stock}.csv",
            mime="text/csv"
        )
    else:
        st.warning("Tidak ada data yang tersedia untuk filter yang dipilih")

# Footer
st.markdown("---")
st.markdown("**Dashboard Analisis Saham** - Data diperbarui: " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
st.caption("Sumber data: Google Cloud Storage | Analisis oleh Sistem Analisis Saham")
