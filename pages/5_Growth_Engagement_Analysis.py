import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

st.set_page_config(page_title="Growth & Engagement", page_icon="🚀", layout="wide")

st.title("🚀 Growth & Engagement Analysis")
st.markdown("### User Acquisition & Retention Metrics")

# --- Dummy Data Generation ---
@st.cache_data
def load_growth_data():
    months = pd.date_range(start='2024-01-01', periods=12, freq='M')
    data = {
        'Month': months,
        'New_Users': np.random.randint(500, 1500, size=12),
        'Active_Users': np.linspace(5000, 12000, 12) + np.random.normal(0, 500, 12),
        'Churn_Rate': np.random.uniform(0.02, 0.08, size=12)
    }
    return pd.DataFrame(data)

df = load_growth_data()

# --- Key Metrics ---
col1, col2, col3 = st.columns(3)
with col1:
    current_mau = df['Active_Users'].iloc[-1]
    prev_mau = df['Active_Users'].iloc[-2]
    growth = ((current_mau - prev_mau) / prev_mau) * 100
    st.metric("Monthly Active Users (MAU)", f"{current_mau:,.0f}", f"{growth:.1f}%")

with col2:
    total_new = df['New_Users'].sum()
    st.metric("Total User Baru (YTD)", f"{total_new:,.0f}")

with col3:
    avg_churn = df['Churn_Rate'].mean() * 100
    st.metric("Rata-rata Churn Rate", f"{avg_churn:.1f}%", "-0.5%")

st.divider()

# --- Visualizations ---
col_chart1, col_chart2 = st.columns([2, 1])

with col_chart1:
    st.subheader("Pertumbuhan User (MAU)")
    fig_growth = px.area(df, x='Month', y='Active_Users', title='Tren Pertumbuhan Active User')
    st.plotly_chart(fig_growth, use_container_width=True)

with col_chart2:
    st.subheader("Korelasi User Baru vs Churn")
    fig_scatter = px.scatter(df, x='New_Users', y='Churn_Rate', size='Active_Users', title='New Users vs Churn Rate')
    st.plotly_chart(fig_scatter, use_container_width=True)

# --- Insights ---
st.subheader("💡 Summary Insights")
st.warning("""
**Growth Trajectory:**
1.  **Tren Positif**: User base tumbuh konsisten sebesar **~15% MoM** (Month over Month).
2.  **Churn Alert**: Meskipun pertumbuhan tinggi, Churn Rate sedikit meningkat di Q3. Perlu program retensi atau loyalty rewards untuk user lama.
3.  **Akuisisi**: Kampanye marketing di bulan Juni terlihat sangat efektif mendatangkan user baru (lihat lonjakan di grafik).
""")
