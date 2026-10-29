# Panduan Pemula: Mengendalikan Motor Stepper

Panduan ini membantu kamu mencoba aplikasi kontrol motor stepper menggunakan
ESP32. Tidak perlu hafal semua istilahnya: ikuti langkah-langkahnya satu per satu.

## 1. Apa yang bisa dilakukan aplikasi ini?

Aplikasi memiliki dua cara menjalankan motor:

- **Continuous**: motor terus berputar setelah tombol START ditekan. Kamu
  memilih arah dan kecepatannya terlebih dahulu.
- **Gas / Manual**: motor bertambah cepat selama tombol gas ditahan, lalu
  melambat saat gas dilepas. Ada juga tombol rem dan pilihan arah.

**CW** berarti searah jarum jam; **CCW** berarti berlawanan arah jarum jam.
Pada mode Gas, keduanya diberi nama **MAJU / CW** dan **MUNDUR / CCW**.

## 2. Persiapan

1. Pastikan ESP32, driver ULN2003, dan motor sudah terhubung sesuai rangkaian.
   Tanyakan kepada guru atau pendamping jika belum yakin dengan sambungannya.
2. Hubungkan ESP32 ke komputer melalui kabel USB.
3. Buka terminal di folder aplikasi, lalu jalankan:

   ```powershell
   python kontrol_motor_final.py
   ```

4. Pada bagian **Koneksi Perangkat**, pilih port ESP32. Jika belum muncul,
   tekan **REFRESH**.
5. Tekan **CONNECT** dan tunggu sampai statusnya **CONNECTED**.

Kalau aplikasi tidak bisa dibuka, pastikan Python, Tkinter, dan `pyserial`
sudah terpasang. Jika port tidak muncul, periksa kabel USB dan sambungannya;
jika port sedang dipakai aplikasi lain, tutup aplikasi tersebut lalu coba lagi.

## 3. Mencoba mode Gas / Manual

Mode ini mirip pedal gas dan rem: tahan untuk menggunakannya, lalu lepaskan.

### Menggunakan keyboard

| Tombol | Kegunaan |
| --- | --- |
| **Shift + ↑** | Memilih maju / CW |
| **Shift + ↓** | Memilih mundur / CCW |
| **Spacebar** | Tahan untuk gas; lepaskan untuk melambat |
| **J** | Tahan untuk rem |
| **1, 2, 3, 4** | Memilih gigi |

Langkah pertama:

1. Pilih **Gas / Manual**.
2. Pilih **gigi 1** dengan tombol angka `1` atau tombol gigi di layar.
3. Tahan **Shift**, tekan **↑** untuk memilih maju, lalu lepaskan keduanya.
4. Tahan **Spacebar** dan perhatikan kecepatan pada layar meningkat.
5. Lepaskan **Spacebar** dan perhatikan motor melambat.
6. Coba tahan **J** untuk memperlambat motor lebih cepat.

Saat sedang mengetik di kolom input, Spacebar dan J dipakai untuk mengetik,
bukan untuk mengendalikan gas atau rem. Klik area lain di aplikasi sebelum
menggunakan shortcut tersebut.

### Menggunakan mouse

1. Klik **CLUTCH** untuk mengaktifkannya.
2. Klik **MAJU / CW** atau **MUNDUR / CCW**. Clutch otomatis nonaktif setelah
   arah dipilih.
3. Tekan dan tahan tombol **GAS** di layar untuk menambah kecepatan. Lepaskan
   tombol mouse untuk melambat.
4. Tekan dan tahan **REM** di layar untuk melambat lebih cepat.

Tombol aktif berubah warna. Petunjuk singkat juga tersedia di layar aplikasi.

### Apa yang terjadi saat berganti arah?

Jika kamu memilih arah yang berlawanan saat motor masih bergerak, motor akan
melambat sampai berhenti terlebih dahulu. Setelah itu, motor dapat bergerak
ke arah baru saat gas ditekan. Jika gas dan rem digunakan bersamaan, **rem
diutamakan**.

### Gigi itu apa?

Gigi menentukan **batas kecepatan maksimum**. Gigi yang lebih tinggi
memungkinkan motor berputar lebih cepat. Gigi dipilih sendiri menggunakan
tombol di layar atau angka `1`–`4` pada keyboard.

| Gigi | Batas maksimum |
| --- | --- |
| 1 | 100 step/s |
| 2 | 250 step/s |
| 3 | 400 step/s |
| 4 | 500 step/s |

*Step/s* berarti jumlah langkah motor per detik. Untuk latihan pertama, mulai
dari gigi 1. Ketika kamu memilih gigi yang lebih rendah saat motor masih cepat,
aplikasi akan melambatkan motor sebelum gigi baru aktif.

## 4. Mencoba mode Continuous

1. Pilih **Continuous**.
2. Pilih kecepatan dengan slider, angka manual, atau tombol preset. Jika
   memasukkan angka sendiri, tekan **SET ANGKA**.
3. Pilih arah **CW** atau **CCW**.
4. Tekan **START MOTOR**. Motor akan terus berputar.
5. Tekan **STOP MOTOR** untuk menghentikannya.

Memilih arah saja saat motor berhenti tidak langsung menyalakannya.

## 5. Menghentikan motor

Di mode Gas, melepaskan gas membuat motor **melambat bertahap**. Tombol
**REM** atau `J` membuatnya melambat lebih cepat. Tombol **STOP MOTOR**
mengirim perintah berhenti langsung dan mereset input.

Setelah menekan STOP saat gas ditahan, lepaskan gas terlebih dahulu, lalu
tekan lagi jika ingin menjalankan motor. Pada mode Gas, berpindah ke aplikasi
lain juga menghentikan dan mereset kontrol.

## 6. Mengganti tema

Tekan **LIGHT** atau **DARK** di bagian atas aplikasi untuk mengganti warna
tampilan. Pilihan tema akan diingat saat aplikasi dibuka kembali.

## 7. Kalau motor belum bergerak

- Pastikan status koneksi **CONNECTED**, bukan hanya CONNECTING.
- Pastikan mode yang dipilih sesuai dengan kontrol yang sedang digunakan.
- Di mode Gas, pilih arah dengan clutch, lalu **tahan** gas; jangan hanya klik
  sebentar. Jika sebelumnya menekan STOP, lepas gas dan tekan ulang.
- Di mode Continuous, tekan **START MOTOR** setelah memilih arah dan kecepatan.
- Periksa pesan di **System Log** dan sambungan perangkat bersama pendamping.

Angka pada speedometer menunjukkan kecepatan yang diperintahkan aplikasi,
bukan hasil pengukuran sensor pada motor.

## 8. Selesai menggunakan

1. Tekan **STOP MOTOR**.
2. Tekan **DISCONNECT**.
3. Tutup aplikasi dan lepaskan perangkat sesuai arahan guru atau pendamping.
