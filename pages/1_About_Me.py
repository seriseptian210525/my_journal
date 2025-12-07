import streamlit as st

st.set_page_config(page_title="About Me", page_icon="👤")

st.title("👤 About Me")

col1, col2 = st.columns([1, 3])

with col1:
    # Ganti "assets/images/profile.png" dengan foto asli Anda
    # REKOMENDASI: Gunakan foto rasio 1:1 (Persegi), minimal 400x400 pixels.
    try:
        st.image("assets/images/profile.png", caption="My Profile Picture", width=300)
    except:
        st.image("https://placehold.co/400", caption="Upload foto ke assets/images/profile.png (Min 400x400px)")

with col2:
    st.markdown("""
    ### Halo! Saya [Nama Anda]
    
    Saya adalah seorang Data Analyst yang gemar mengubah data mentah menjadi insight yang bermakna.
    
    **Keahlian:**
    - Python (Pandas, NumPy)
    - Data Visualization (Streamlit, Plotly)
    - SQL
    - Machine Learning Basics
    
    **Kontak:**
    - LinkedIn: [linkedin.com/in/username](https://linkedin.com)
    - GitHub: [github.com/username](https://github.com)
    - Email: email@example.com
    """)

st.divider()

st.subheader("Riwayat Pendidikan & Karir")
st.info("Tambahkan detail pendidikan atau pengalaman kerja di sini.")
