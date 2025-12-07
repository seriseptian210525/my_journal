import streamlit as st

st.set_page_config(
    page_title="My Analytics Journal",
    page_icon="📊",
    layout="wide"
)

st.title("📊 My Analytics Journal")

st.markdown("""
### Selamat Datang di Dashboard Jurnal Analisa Saya!

Aplikasi ini berfungsi sebagai portofolio dan dokumentasi dari berbagai project analisa data yang telah saya kerjakan.

**Navigasi:**
- Gunakan sidebar di sebelah kiri untuk berpindah halaman.
- **About Me**: Informasi tentang saya.
- **Project Analysis**: Template untuk melihat detail analisa per project.

---
*Built with Streamlit*
""")

st.sidebar.success("Pilih halaman di atas.")
