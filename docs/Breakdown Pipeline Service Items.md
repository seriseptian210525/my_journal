# **Breakdown Pipeline Data ELSA Service Items (Modular OOP)**

Dokumen ini menjelaskan arsitektur, logika bisnis, dan alur data untuk pipeline Catatan Servis ELSA, dengan penekanan khusus pada transisi ke sistem **Warranty** kategorikal.

## **1\. Ringkasan Eksekutif**

Pipeline ini mengubah data mentah servis ELSA menjadi data yang sudah diperkaya dan dibersihkan. Tujuan utamanya adalah menentukan status "Warranty" dari item servis menggunakan sistem logika berbasis prioritas. Pipeline ini mengintegrasikan data dari tiga sumber utama:

* **Data Mentah ELSA**: Log servis dan perintah kerja (work orders).  
* **Mapping Part**: Pola regex serta metadata harga dan SKU.  
* **Database Motor (SCM)**: Tanggal pengiriman motor dan informasi pemilik.

## **2\. Arsitektur Inti (Kapabilitas Bisnis)**

Pipeline ini disusun menjadi 8 "Kapabilitas Bisnis" yang berbeda, masing-masing mewakili modul spesifik dalam siklus data:

1. **Environment Setup**: Mengelola dependensi (fuzzywuzzy), mounting Google Drive, dan mengatur path sistem untuk modul kustom.  
2. **Pipeline Config**: Sebagai **Single Source of Truth**. Berisi ID GSheet, definisi flag kategorikal, dan ambang batas logika (misalnya, FUZZY\_THRESHOLD).  
3. **Data Loader**: Khusus menangani operasi IO untuk mengambil dataframe dari Google Sheets.  
4. **Data Transformer**: Mengelola perubahan struktural data.  
   * **Transpose**: Memecah string multi-item (misal: "Ban & Rem") menjadi baris individu.  
   * **Regex Mapping**: Mencocokkan nama mentah ke nama part standar berdasarkan pola kompleks.  
   * **Fuzzy Matching**: Mekanisme fallback untuk menangani typo menggunakan jarak Levenshtein.  
5. **Data Enricher**: "Otak" dari pipeline. Modul ini menggabungkan database eksternal dan menghitung flag **Warranty**.  
6. **Pipeline Orchestrator**: Konduktor yang merangkai semua modul. Memastikan data mengalir melalui transformer dan enricher dalam urutan yang benar.  
7. **Data Exporter**: Menangani output akhir, menulis ulang data di GSheet tujuan dan menyimpan cadangan CSV dengan timestamp.  
8. **Testing & Assertions**: Memvalidasi output terhadap aturan bisnis sebelum dinyatakan sukses.

## **3\. Logika Warranty Baru**

Pipeline telah beralih dari flag "Coverage" biner ke sistem **Warranty** kategorikal. Logika diterapkan secara **top-down** (berdasarkan prioritas):

| Flag | Prioritas | Kondisi Pemicu |
| :---- | :---- | :---- |
| **PACKAGE\_SERVICE** | 1 (Tertinggi) | Part spesifik (Ban/Kampas Rem) dalam batas pemakaian (misal: ban ke 1-2, kampas rem ke 1-6). |
| **WARRANT** | 2 | Umur motor (Bulan Ke) kurang dari Periode Garansi yang didefinisikan dalam mapping part. |
| **INSURANCE** | 3 | Part yang tidak masuk kategori PACKAGE\_SERVICE atau WARRANT, namun berkaitan dengan *body part*, *frame*, *plate number \+ cover*, atau spion (*rear mirror*). |
| **NOT\_COVERED** | 4 (Default) | Status berbayar (kondisi default jika tidak memenuhi kriteria garansi/jaminan apa pun). |

## **4\. Transformasi Data Kunci**

### **Normalisasi Data**

* **Delimiter**: Mendukung pemisahan pada karakter ,, \\n, dan, &, dan /.  
* **Odometer**: Menghapus karakter non-numerik dan mengubahnya menjadi integer untuk perhitungan.  
* **Penggabungan (Joining)**: Memetakan kolom Plat Nomor dari database pendukung ke primary key vehicle\_license\_plate dengan benar.

### **Kontrol Kualitas**

* **Validasi Regex**: Secara otomatis menyaring pola regex yang tidak valid di sheet mapping untuk mencegah error saat runtime.  
* **Ambang Batas Fuzzy**: Dikontrol via config (default 85%) untuk memastikan akurasi mapping yang tinggi.  
* **Deduplikasi**: Mencegah penghitungan ganda item servis dalam satu order\_id yang sama untuk perhitungan urutan (sequence).

## **5\. Definisi Selesai (Definition of Done)**

Pipeline dianggap sehat jika:

* \[ \] Environment telah terpasang dan modul telah dimuat.  
* \[ \] Tidak ada nilai null pada kolom Rekomendasi Nama Part Baru.  
* \[ \] Flag Warranty berada dalam set kategori yang telah ditentukan.  
* \[ \] Semua pernyataan assert dalam cell Testing berhasil dilewati.  
* \[ \] Output akhir berhasil diunggah ke Master Sheet ELSA.