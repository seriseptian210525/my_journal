import streamlit as st

st.set_page_config(page_title="About Me", page_icon="👤")

st.title("👤 About Me")

col1, col2 = st.columns([1.5, 2.5])

with col1:
    # Ganti "assets/images/profile.png" dengan foto asli Anda
    # REKOMENDASI: Gunakan foto rasio 1:1 (Persegi), minimal 400x400 pixels.
    try:
        # Gunakan use_container_width agar responsif dan tidak menabrak kolom sebelah
        st.image("assets/images/profile.png", caption="My Profile Picture", use_container_width=True)
    except:
        st.image("https://placehold.co/400", caption="Upload foto ke assets/images/profile.png (Min 400x400px)", use_container_width=True)

with col2:
    st.markdown("""
    ### Halo! Saya [Nama Anda]
    
    Saya adalah seorang Data Analyst yang gemar mengubah data mentah menjadi insight yang bermakna.
    
    **Keahlian:**
    - Python (Pandas EDA)
    - Data Visualization (Streamlit, Lookers Studio)
    - SQL Basic
    
    **Kontak:**
    - LinkedIn: [linkedin.com/in/username](https://linkedin.com)
    - GitHub: [github.com/username](https://github.com)
    - Email: seri.septian@electrum.id
    """)

st.divider()

st.subheader("Riwayat Pendidikan & Karir")
st.info("Tambahkan detail pendidikan atau pengalaman kerja di sini.")
