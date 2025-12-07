# Dokumentasi Struktur Project

Dokumen ini menjelaskan struktur folder dan file untuk aplikasi "My Analytics Journal". Struktur ini dirancang agar mudah dikembangkan seiring bertambahnya project portofolio.

## Struktur Utama

```text
my_journal/
├── app.py                   # Entry point utama aplikasi Streamlit
├── project_structure.md     # (File ini) Dokumentasi struktur project
├── requirements.txt         # Dependencies untuk aplikasi utama Streamlit
├── pages/                   # Folder halaman-halaman Streamlit
│   ├── 1_About_Me.py        # Halaman profil
│   ├── 2_Fleet_Analysis.py  # Halaman analisa Fleet
│   ├── 3_After_Sales_Analysis.py # Halaman analisa After Sales (sebelumnya Project Pertama)
│   ├── 4_ERA_Support.py     # Halaman analisa ERA Support
│   └── 5_Growth_Engagement_Analysis.py # Halaman analisa Growth & Engagement
└── projects/                # Folder penampung kode sumber (source code) setiap project
    └── my_etl_project/      # Folder source code (bisa disesuaikan namanya nanti)
        ├── .github/
        │   └── workflows/
        │       └── daily_etl.yml
        ├── src/
        │   ├── main.py
        │   ├── data_loader.py
        │   ├── transformers.py
        │   └── config.py
        ├── requirements.txt
        └── credentials/
            └── seri-automation-etl.json
```

## Penjelasan Halaman (Objectives)

1.  **Fleet Analysis**: Analisa terkait armada operasional.
2.  **After Sales Analysis**: Analisa purna jual (sebelumnya project ETL).
3.  **ERA Support**: Analisa terkait Emergency Roadside Assistance.
4.  **Growth & Engagement Analysis**: Analisa pertumbuhan dan keterlibatan pengguna.

## Cara Menambah Project Baru

1.  **Buat Folder Project**: Buat folder baru di dalam `projects/` (misal `projects/sales_forecasting/`).
2.  **Isi Kode**: Masukkan script, notebook, atau data terkait project tersebut ke dalam folder yang baru dibuat.
3.  **Buat Halaman Dashboard**: Buat file baru di `pages/` dengan nomor urut selanjutnya (misal `6_New_Project.py`).
4.  **Hubungkan**: Di dalam file halaman tersebut, import kode atau tampilkan hasil visualisasi.
