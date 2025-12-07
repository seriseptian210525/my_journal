import streamlit as st

# Page Configuration
st.set_page_config(
    page_title="Home",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Header
st.title("🏠 Home - My Analytics Journal")
st.markdown("### Portofolio & Jurnal Analisa Data")
st.divider()

# Dashboard Objective
st.markdown("""
#### 🎯 Tujuan Dashboard
Dashboard ini dirancang sebagai pusat dokumentasi dan visualisasi dari perjalanan saya dalam menganalisa data. 
Setiap halaman di sidebar mewakili **project independen** yang mengeksplorasi berbagai aspek bisnis dan operasional.

Tujuannya adalah:
1.  **Showcase**: Menampilkan kemampuan teknis dalam ETL, Visualisasi, dan Insight Generation.
2.  **Documentation**: Menyimpan metodologi dan temuan dari setiap analisa.
3.  **Monitoring**: (Untuk project tertentu) Memantau metrik operasional secara real-time.
""")

st.divider()

# Page Overviews
st.markdown("#### 📂 Daftar Modul Analisa")
st.markdown("Berikut adalah ringkasan dari modul-modul yang tersedia di dashboard ini:")

# Using columns for better layout
col1, col2 = st.columns(2)

with col1:
    with st.expander("👤 About Me", expanded=True):
        st.markdown("**Page 1**")
        st.info("Informasi singkat tentang profil profesional saya, pengalaman, dan keahlian teknis.")

    with st.expander("🚚 Fleet Analysis", expanded=True):
        st.markdown("**Page 2**")
        st.info("Analisa performa armada, efisiensi bahan bakar, dan utilisasi kendaraan operasional.")

    with st.expander("🛠️ After Sales Analysis (Featured)", expanded=True):
        st.markdown("**Page 3**")
        st.success("Analisa mendalam tentang Work Orders, Sparepart, dan Keluhan Pelanggan. Menggunakan data yang diproses via modular ETL Pipeline.")

with col2:
    with st.expander("🆘 ERA Support", expanded=True):
        st.markdown("**Page 4**")
        st.warning("Analisa layanan Emergency Roadside Assistance (ERA), response time, dan distribusi kejadian.")

    with st.expander("📈 Growth & Engagement", expanded=True):
        st.markdown("**Page 5**")
        st.info("Analisa pertumbuhan user, retensi, dan tingkat interaksi (engagement) pada platform.")


# Footer/Sidebar Info
st.sidebar.info("Pilih modul di atas untuk melihat detail analisa.")
st.markdown("---")
st.caption("© 2025 My Analytics Journal | Build with Streamlit & Python")
