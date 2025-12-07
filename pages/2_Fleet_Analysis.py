import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

st.set_page_config(page_title="Fleet Analysis", page_icon="🚛", layout="wide")

st.title("🚛 Fleet Analysis")
st.markdown("### Overview Operational Armada")

# --- Dummy Data Generation ---
@st.cache_data
def load_fleet_data():
    np.random.seed(42)
    n_records = 100
    data = {
        'Vehicle_ID': [f'V-{i:03d}' for i in range(n_records)],
        'Type': np.random.choice(['Truck', 'Van', 'Motorcycle'], n_records),
        'Status': np.random.choice(['Active', 'Maintenance', 'Idle'], n_records, p=[0.7, 0.1, 0.2]),
        'Fuel_Efficiency_km_l': np.random.uniform(5, 15, n_records),
        'Maintenance_Cost_IDR': np.random.uniform(500000, 5000000, n_records)
    }
    return pd.DataFrame(data)

df = load_fleet_data()

# --- Key Metrics ---
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Armada", len(df))
with col2:
    active_count = len(df[df['Status'] == 'Active'])
    st.metric("Armada Aktif", active_count, f"{active_count/len(df)*100:.1f}%")
with col3:
    avg_cost = df['Maintenance_Cost_IDR'].mean()
    st.metric("Rata-rata Biaya Maintenance", f"Rp {avg_cost:,.0f}")

st.divider()

# --- Visualizations ---
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("Distribusi Status Armada")
    fig_status = px.pie(df, names='Status', title='Persentase Status Kendaraan', hole=0.4)
    st.plotly_chart(fig_status, use_container_width=True)

with col_chart2:
    st.subheader("Biaya Maintenance per Tipe")
    fig_cost = px.box(df, x='Type', y='Maintenance_Cost_IDR', color='Type', title='Distribusi Biaya per Tipe Kendaraan')
    st.plotly_chart(fig_cost, use_container_width=True)

# --- Insights ---
st.subheader("💡 Summary Insights")
st.info("""
**Observasi Awal:**
1.  **Ketersediaan Armada**: 70% armada dalam kondisi *Active*, yang merupakan angka sehat untuk operasional harian.
2.  **Biaya Tinggi pada Truck**: Terlihat variasi biaya maintenance yang cukup besar pada tipe *Truck*, perlu investigasi lebih lanjut apakah disebabkan oleh umur kendaraan atau rute berat.
3.  **Idle Capacity**: 20% armada dalam kondisi *Idle*. Bisa dipertimbangkan untuk optimasi rute atau pengurangan armada jika tren berlanjut.
""")
