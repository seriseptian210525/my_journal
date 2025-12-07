import streamlit as st

st.set_page_config(page_title="About Me", page_icon="👤")

st.title("👤 About Me")

col1, col2 = st.columns([1, 3])

with col1:
    st.image("https://placehold.co/400", caption="My Profile Picture")

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
