# **Data Pipeline Column Configuration HISTORICAL_SERVICE.ipynb**

Dokumen ini menjelaskan konfigurasi kolom untuk setiap variabel DataFrame sumber sebelum dilakukan proses pd.concat ke dalam DataFrame utama **all\_elsa\_history**.

## **Target Schema (all\_elsa\_history)**

Semua variabel sumber di bawah ini akan dipetakan dan dinormalisasi agar sesuai dengan skema akhir berikut:

| Column Name | Tipe Data | Deskripsi |
| :---- | :---- | :---- |
| created\_at | Datetime | Waktu pembuatan tiket/order (Generated/Randomized logic). |
| updated\_at | Datetime | Waktu update terakhir (Generated). |
| completed\_at | Datetime | Waktu penyelesaian servis (Generated). |
| service\_type | String | Kategori layanan (e.g., Regular, Urgent, Broken Unit). |
| order\_status | String | Status order (Default: 'COMPLETED'). |
| service\_location\_name | String | Nama lokasi servis (e.g., Pondok Indah, Kembangan). |
| customer\_name | String | Nama driver atau "Sahabat Electrum". |
| vehicle\_license\_plate | String | Plat nomor kendaraan (Format: B 1234 XYZ). |
| vechicle\_vin | String | Nomor Rangka (VIN). |
| vechicle\_engine | String | Nomor Mesin. |
| completed\_by | String | Nama mekanik yang mengerjakan. |
| odometer | Integer | Jarak tempuh kendaraan (Estimated/Actual). |
| bike\_type | String | Model motor (H3, H5). |

## **Source Variables Configuration**

Berikut adalah detail variabel yang digabungkan:

### **1\. elsa\_tracker1**
S1_FORM_SERVICE.columns = ['Timestamp','Lokasi Pool','Bike Model', 'Nama Driver (1)', 'Nama Driver', 'Driver Category', 'ODO / KM', 'Plate Number (1)','Plat Nomor', 'Tanggal Service', 'Nama Mekanik', 'Jam Registrasi', 'Jam Mulai Service', 'Jam Selesai Service', 'Jam Serah Terima Unit ke Driver','Mechanic Action Category', 'Keluhan Driver', 'Tindakan Dari Mekanik', 'Total Biaya Perbaikan', 'Apakah Ada Pergantian Part H5', 'Apakah Ada Pergantian Part H3', 'Nama Part yang diganti','Part lain yang diganti (1)', 'Part lain yang diganti (2)', 'Part lain yang diganti (3)', 'Part lain yang diganti (4)', 'Part lain yang diganti (5)']

* **Source:** "FORM SERVICE ELECTRUM 2025 (26June) (Responses)" \-\> form1  
* **Logic:** Service Reguler & Driver Visit  
* **Hardcoded Values:**  
  * order\_status: 'COMPLETED'  
* **Column Mapping:**

| Source Column (Raw/Renamed) | Target Column |
| :---- | :---- |
| *(Calculated Timestamp)* | created\_at |
| *(Calculated Timestamp)* | updated\_at |
| *(Calculated Timestamp)* | completed\_at |
| service\_type (from Mechanic Action Category) | service\_type |
| Lokasi Pool | service\_location\_name |
| Nama Driver (1) | customer\_name |
| Plat Nomor | vehicle\_license\_plate |
| Nama Mekanik | completed\_by |
| ODO / KM | odometer |

### **2\. elsa\_tracker2**
'S2_SERVICE_GRAB'.columns = ['Tanggal Selesai Service','Tanggal Service','Nama Mekanik','Bike Model','Plat Nomor','ODO / KM','Mechanic Action Category','Keluhan Driver','Tindakan Dari Mekanik','Apakah ada pergantian sparepart?','Consumable Part yang diganti','Sparepart lain yang diganti','2. Part lain yang diganti','3. Part lain yang diganti','4. Part lain yang diganti', '5. Part lain yang diganti', 'Email address', 'Lokasi Pool','Foto Tampak Depan (Nopol Jelas)', 'Column 18', 'Sparepart yang diganti']


* **Source:** "Service Unit Grab Electrum" \-\> form2  
* **Logic:** Data Grab & Official Partner  
* **Hardcoded Values:**  
  * Nama Driver: 'Driver Grab'  
  * order\_status: 'COMPLETED'  
* **Column Mapping:**

| Source Column (Raw/Renamed) | Target Column |
| :---- | :---- |
| *(Calculated Timestamp)* | created\_at |
| *(Calculated Timestamp)* | updated\_at |
| Tanggal Selesai Service | completed\_at |
| Tindakan Dari Mekanik (Mapped Logic) | service\_type |
| Lokasi Pool | service\_location\_name |
| Plat Nomor | vehicle\_license\_plate |
| Nama Mekanik | completed\_by |
| ODO/KM | odometer |

### **3\. elsa\_tracker3**
'S3_FORM_RESPONSES'.columns = ['Timestamp', 'Lokasi Pool', 'Nama Driver', 'Driver Category', 'Tanggal Service', 'Plat Nomor', 'odometer', 'Mechanic Action Category', 'Mechanic Name', 'Jam Registrasi', 'Jam Mulai Service', 'Jam Selesai Service', 'Jam Serah Terima Unit ke Driver', 'Keluhan Driver', 'Tindakan dari Mekanik', 'Bike Model', 'Apakah Ada Pergantian Part H5', 'Apakah Ada Pergantian Part H3', 'Fast Moving Part (H5)', 'Medium Moving Part (H5)', 'Slow Moving Part (H5)', 'Fast Moving Part (H3)', 'Medium Moving Part (H3)', 'Slow Moving Part (H3)', 'Category Kerusakan', 'Total Biaya Perbaikan ', 'Perbaikan dari Mekanik', 'Apakah Ada Pergantian Part H1', 'Fast Moving Part (H1)', 'Medium Moving Part (H1)', 'Slow Moving Part (H1)', 'Perbaikan yang dilakukan', 'Column 29']

* **Source:** "FORM SERVICE ELECTRUM 2025 (26June) (Responses)" \-\> form3  
* **Logic:** Form respons kedua (lanjutan)  
* **Hardcoded Values:**  
  * order\_status: 'COMPLETED'  
* **Column Mapping:**

| Source Column (Raw/Renamed) | Target Column |
| :---- | :---- |
| *(Calculated Timestamp)* | created\_at |
| *(Calculated Timestamp)* | updated\_at |
| *(Calculated Timestamp)* | completed\_at |
| Mechanic Action Category | service\_type |
| Lokasi Pool | service\_location\_name |
| Nama Driver | customer\_name |
| Plat Nomor | vehicle\_license\_plate |
| Nama Mekanik | completed\_by |

### **4\. elsa\_ex\_tracker**
S4_REQUEST_SPK.columns = ['Nomor Servis', 'Tanggal Service', 'vechicle_engine', 'vechicle_vin', 'customer_name', 'Nomer Telepon Driver', 'bike_type', 'vehicle_license_plate', 'odometer', 'customer_problems', 'Alamat Email', 'Item Suspect', 'customer_type', 'Foto Kerusakan', 'Foto Odo / Kilometer', 'Tanggal Konfirmasi', 'Catatan Hasil Konfirmasi', 'item_name', 'Harga Part', 'Jasa', 'Konfirmasi Pembayaran', 'Bukti Bayar', 'service_location_name', 'Alamat Bengkel', 'completed_by', 'Nama Cabang', 'Tanggal Terbit SPK', 'Nomor SPK', 'Tanggal Service di Bengkel', 'Tanggal Survey CSAT', 'Nilai CSAT (1 s.d. 5)', 'Tgl Service by konfirmasi', 'Keterangan', 'Complain', 'Detail Complain', 'Status', 'Buat SPK', 'Cetak SPK', 'Item Pengerjaan', 'Status SPK', 'Keluhan Driver', 'Tindakan Dari Mekanik', 'service_type','order_status','color', 'created_at', 'updated_at', 'completed_at', 'prize_finalized_at','total_price']

* **Source:** "LIST REQUEST SPK" \-\> ex\_afs  
* **Logic:** Data SPK (Surat Perintah Kerja)  
* **Hardcoded Values:**  
  * Mechanic Action Category: 'Official Partner Service'  
  * order\_status: 'COMPLETED'  
* **Column Mapping:**

| Source Column (Raw/Renamed) | Target Column |
| :---- | :---- |
| *(Calculated Timestamp)* | created\_at |
| *(Calculated Timestamp)* | updated\_at |
| *(Calculated Timestamp)* | completed\_at |
| Official Partner Service (Static) | service\_type |
| Bengkel Tujuan | service\_location\_name |
| Nama Driver | customer\_name |
| Plat Nomor | vehicle\_license\_plate |
| vechicle\_vin | vechicle\_vin |
| vechicle\_engine | vechicle\_engine |

### **5\. elsa\_repair\_pi\_tracker**
'S5_AFTER_REPAIR'.columns = ['Tanggal Service', 'vehicle_license_plate', 'completed_by', 'bike_type', 'item_name', 'service_type', 'service_location_name', 'odometer', 'customer_problems', 'customer_name', 'order_status', 'Tindakan Dari Mekanik', 'created_at', 'updated_at', 'completed_at', 'prize_finalized_at', "vechicle_vin","vechicle_engine",'color', 'customer_type','total_price']

* **Source:** "BREAKDOWN NG" \-\> aft\_repair / all\_repair  
* **Logic:** After Repair (Pondok Indah)  
* **Hardcoded Values:**  
  * Lokasi Pool: 'Pondok Indah'  
  * Nama Driver: 'Sahabat Electrum'  
  * Mechanic Action Category: 'Broken Unit'  
  * order\_status: 'COMPLETED'  
* **Column Mapping:**

| Source Column (Raw/Renamed) | Target Column |
| :---- | :---- |
| *(Calculated Timestamp)* | created\_at |
| *(Calculated Timestamp)* | updated\_at |
| *(Calculated Timestamp)* | completed\_at |
| Broken Unit (Static) | service\_type |
| Pondok Indah (Static) | service\_location\_name |
| Sahabat Electrum (Static) | customer\_name |
| vehicle\_license\_plate | vehicle\_license\_plate |
| completed\_by | completed\_by |
| bike\_type | bike\_type |

### **6\. tracker\_elsa\_kembangan**

* **Source:** "VIEW CABANG Kembangan NG" \-\> kembangan  
* **Logic:** Data Cabang Kembangan  
* **Hardcoded Values:**  
  * service\_location\_name: 'Kembangan'  
  * customer\_name: 'Sahabat Electrum'  
  * service\_type: 'Broken Unit'  
  * order\_status: 'COMPLETED'  
* **Column Mapping:**

| Source Column (Raw/Renamed) | Target Column |
| :---- | :---- |
| *(Calculated Timestamp)* | created\_at |
| *(Calculated Timestamp)* | updated\_at |
| *(Calculated Timestamp)* | completed\_at |
| Broken Unit (Static) | service\_type |
| Kembangan (Static) | service\_location\_name |
| vehicle\_license\_plate | vehicle\_license\_plate |
| completed\_by | completed\_by |

### **7\. tracker\_elsa\_depok**
'S7_DEPOK'.columns = ['customer_name', 'service_location_name', 'Tanggal Service', 'service_type', 'completed_by', 'bike_type', 'vehicle_license_plate', 'odometer', 'customer_problems', 'Tindakan Dari Mekanik', 'item_name', 'order_status', "vechicle_vin","vechicle_engine", 'color','customer_type','created_at', 'updated_at', 'completed_at', 'prize_finalized_at', 'total_price']
* **Source:** "Tracker Sparepart WH Depok" \-\> depok  
* **Logic:** Data Cabang Depok (Filter: 'Reduce NG')  
* **Hardcoded Values:**  
  * service\_location\_name: 'Depok'  
  * order\_status: 'COMPLETED'  
* **Column Mapping:**

| Source Column (Raw/Renamed) | Target Column |
| :---- | :---- |
| *(Calculated Timestamp)* | created\_at |
| *(Calculated Timestamp)* | updated\_at |
| *(Calculated Timestamp)* | completed\_at |
| service\_type | service\_type |
| Depok (Static) | service\_location\_name |
| customer\_name | customer\_name |
| Plat Nomor | vehicle\_license\_plate |
| Nama Mekanik | completed\_by |

### **8\. tracker\_elsa\_bekasi**
'S8_BEKASI'.columns = ['Timestamp', 'Tanggal Service', 'bike_type', 'Plat Nomor', 'Sparepart yang diganti - H3 ONLY', 'Sparepart yang diganti - H5 ONLY', 'Nama Mekanik', 'Status Unit', 'Perbaikan & Rpc', 'ALL SPAREPART', 'BAHAN BAKU', 'Column 8', 'item_name', 'service_type', 'service_location_name', 'odometer', 'customer_problems', 'customer_name', 'Tindakan Dari Mekanik']

* **Source:** "form Repair Bike Bekasi" \-\> bekasi  
* **Logic:** Data Cabang Bekasi  
* **Hardcoded Values:**  
  * service\_location\_name: 'Bekasi'  
  * customer\_name: 'Sahabat Electrum'  
  * service\_type: 'Broken Unit'  
  * order\_status: 'COMPLETED'  
  * odometer: 0  
* **Column Mapping:**

| Source Column (Raw/Renamed) | Target Column |
| :---- | :---- |
| *(Calculated Timestamp)* | created\_at |
| *(Calculated Timestamp)* | updated\_at |
| *(Calculated Timestamp)* | completed\_at |
| Broken Unit (Static) | service\_type |
| Bekasi (Static) | service\_location\_name |
| vehicle\_license\_plate | vehicle\_license\_plate |
| bike\_type | bike\_type |

**Note:** Setelah penggabungan (pd.concat), akan dilakukan Advanced Cleaning (LogicVIN1, LogicVIN2, LogicOdo, & MechanicStandardization) sebelum data siap digunakan.