import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

st.set_page_config(page_title="ERA Support", page_icon="🚑", layout="wide")

st.title("🚑 ERA Support Analysis")
st.markdown("### Emergency Roadside Assistance Performance")

# --- Dummy Data Generation ---
@st.cache_data
def load_era_data():
    dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
    data = {
        'Date': dates,
        'Incidents': np.random.randint(10, 50, size=30),
        'Avg_Response_Time_Mins': np.random.uniform(15, 45, size=30),
        'Customer_Rating': np.random.uniform(3.5, 5.0, size=30)
    }
    return pd.DataFrame(data)

df = load_era_data()

# --- Key Metrics ---
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Insiden (30 Hari)", df['Incidents'].sum())
with col2:
    avg_resp = df['Avg_Response_Time_Mins'].mean()
    st.metric("Rata-rata Response Time", f"{avg_resp:.1f} Menit", "-2.5 Menit")
with col3:
    avg_rating = df['Customer_Rating'].mean()
    st.metric("Customer Satisfaction Score", f"{avg_rating:.1f}/5.0", "+0.2")

st.divider()

# --- Visualizations ---
st.subheader("Tren Harian")
tab1, tab2 = st.tabs(["Response Time", "Volume Insiden"])

with tab1:
    fig_resp = px.line(df, x='Date', y='Avg_Response_Time_Mins', markers=True, title='Tren Waktu Respon Harian')
    fig_resp.add_hline(y=30, line_dash="dash", line_color="red", annotation_text="Target SLA (30 min)")
    st.plotly_chart(fig_resp, use_container_width=True)

with tab2:
    fig_vol = px.bar(df, x='Date', y='Incidents', title='Volume Insiden Harian')
    st.plotly_chart(fig_vol, use_container_width=True)

# --- Insights ---
st.subheader("💡 Summary Insights")
st.success("""
**Analisa Performa:**
1.  **Pencapaian SLA**: Rata-rata waktu respon saat ini berada di angka **28.5 menit**, yang mana sudah memenuhi target SLA (30 menit).
2.  **Lonjakan Insiden**: Terdeteksi lonjakan insiden pada akhir pekan. Disarankan menambah personel standby di hari Sabtu-Minggu.
3.  **Kepuasan Pelanggan**: Rating stabil di angka 4.5+, menunjukkan kualitas pelayanan di lapangan sangat baik meskipun volume tinggi.
""")
