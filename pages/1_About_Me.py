import streamlit as st

st.set_page_config(page_title="About Me", page_icon="👤")

# Custom CSS untuk profile image agar portrait tetap bagus
st.markdown("""
<style>
    .profile-container {
        display: flex;
        justify-content: center;
        align-items: center;
    }
    .profile-container img {
        max-height: 350px;
        width: auto;
        object-fit: cover;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
</style>
""", unsafe_allow_html=True)

st.title("👤 About Me")

col1, col2 = st.columns([1.5, 2.5])

with col1:
    # Support untuk gambar portrait maupun square
    # Max height dibatasi 350px agar tidak terlalu tinggi
    import base64
    from pathlib import Path
    
    def get_image_html(image_path, alt_text="Profile Picture"):
        """Convert image to base64 HTML with controlled sizing"""
        try:
            img_path = Path(image_path)
            if img_path.exists():
                with open(img_path, "rb") as f:
                    data = base64.b64encode(f.read()).decode()
                ext = img_path.suffix.lower().replace(".", "")
                if ext == "jpg":
                    ext = "jpeg"
                return f'<div class="profile-container"><img src="data:image/{ext};base64,{data}" alt="{alt_text}"></div>'
        except Exception:
            pass
        return None
    
    # Try multiple extensions (case variations)
    img_html = None
    for ext in ["png", "PNG", "jpg", "JPG", "jpeg", "JPEG"]:
        img_html = get_image_html(f"assets/images/profile.{ext}")
        if img_html:
            break
    
    if img_html:
        st.markdown(img_html, unsafe_allow_html=True)
        st.caption("My Profile Picture")
    else:
        st.image("https://placehold.co/400", caption="Upload foto ke assets/images/profile.png")

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
