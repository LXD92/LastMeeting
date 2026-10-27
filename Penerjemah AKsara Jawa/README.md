# Hanacaraka

Website transliterasi Latin ke Aksara Jawa yang berjalan langsung di browser. Tidak memerlukan backend, instalasi paket, atau server khusus; buka `index.html` di browser.

## Menjalankan

1. Di VS Code pilih **File > Open Folder**, lalu buat atau pilih folder proyek, misalnya `jawa-translator`. Folder workspace yang sudah terbuka juga dapat dipakai sebagai root proyek.
2. Pastikan `index.html`, `style.css`, `script.js`, dan `README.md` berada langsung di root proyek.
3. Buka `index.html` di browser dari File Explorer, atau gunakan ekstensi Live Server jika tersedia.
4. Ketik teks, lalu tunggu hasil diperbarui otomatis atau tekan **Terjemahkan**.

Semua pemrosesan dilakukan lokal. Tombol tema, sisip `é`, ukuran teks, pilihan font, contoh, hapus, salin, dan unduh TXT bekerja tanpa backend. Noto Sans Javanese dimuat dari Google Fonts jika internet tersedia; tanpa internet browser memakai font sistem yang tersedia.

## Cakupan aturan

Mesin di `script.js` adalah implementasi aturan ringan, bukan kamus atau mesin linguistik lengkap. Ia mengubah gugus konsonan menjadi rangkaian aksara dengan pangkon Unicode (yang biasanya dirender sebagai pasangan oleh font), memakai sandhangan untuk vokal `i`, `u`, `e`, `é`/`è`, dan `o`, serta memakai layar, wignyan, dan cecak untuk konsonan akhir `r`, `h`, dan `ng`. Ejaan Latin tanpa diakritik `e` ditafsirkan sebagai pepet; tulis `é` untuk taling.

Keterbatasan yang perlu diperhatikan:

- Ejaan yang sama dapat mewakili pelafalan berbeda; transliterasi tidak dapat menebak makna atau dialek.
- Penentuan pasangan masih memakai pemenggalan gugus konsonan sederhana; gugus, sandhangan, atau coda kompleks mungkin memerlukan koreksi.
- Aksara murda, aksara swara khusus, pada/tanda baca tradisional, dan aturan penulisan nama/serapan belum diterapkan sebagai aturan ortografis.
- Digit ASCII `0`-`9` dipetakan ke angka Jawa Unicode; tanda baca Latin, spasi, dan karakter lain yang tidak dipetakan dipertahankan. Huruf Latin kapital dikenali tanpa padanan kapital khusus di Aksara Jawa.
- Font memengaruhi bentuk pasangan dan sandhangan. Jika tampilan kurang tepat, coba pasang Noto Sans Javanese pada sistem.

Karena batas tersebut, gunakan hasil sebagai draf transliterasi dan periksa kembali untuk kebutuhan formal atau publikasi.

## Pengujian cepat

Dengan Node.js terpasang, jalankan perintah berikut di terminal folder proyek:

```sh
node -e "const assert=require('node:assert/strict'); const t=require('./script.js'); assert.equal(t.transliterate('aku'), '\uA9B2\uA98F\uA9B8'); assert.equal(t.transliterate('Aku'), t.transliterate('aku')); assert.equal(t.prepareInput('Aku Bocah', 'lowercase'), 'aku bocah'); assert.equal(t.prepareInput('Aku Bocah', 'preserve'), 'Aku Bocah'); assert.equal(t.transliterate('aku, ya!'), '\uA9B2\uA98F\uA9B8, \uA9AA!'); assert.equal(t.transliterate('bocah'), '\uA9A7\uA9BA\uA9B4\uA995\uA983'); assert.equal(t.transliterate('anak'), '\uA9B2\uA9A4\uA98F\uA9C0'); assert.equal(t.transliterate('tha'), '\uA99B'); assert.equal(t.transliterate('dha'), '\uA99D'); assert.equal(t.transliterate('ke'), '\uA98F\uA9BC'); assert.equal(t.transliterate('ké'), '\uA98F\uA9BA'); assert.equal(t.transliterate('ko'), '\uA98F\uA9BA\uA9B4'); assert.equal(t.transliterate('kra'), '\uA98F\uA9C0\uA9AB'); assert.equal(t.transliterate('á'), 'á'); console.log('Semua pemeriksaan dasar lulus');"
```

Tes angka Jawa:

```sh
node -e "const assert=require('node:assert/strict'); const t=require('./script.js'); assert.equal(t.transliterate('0123456789'), String.fromCodePoint(0xA9D0,0xA9D1,0xA9D2,0xA9D3,0xA9D4,0xA9D5,0xA9D6,0xA9D7,0xA9D8,0xA9D9)); assert.equal(t.transliterate('tahun 2026!'), t.transliterate('tahun')+' '+String.fromCodePoint(0xA9D2,0xA9D0,0xA9D2,0xA9D6)+'!'); console.log('Tes angka Jawa lulus');"
```

Checklist antarmuka di browser:

- Ketik `Aku Bocah Sing Sregep Banget.`; hasil berubah otomatis.
- Coba `Tahun 2026.`; digit tampil sebagai angka Jawa dan titik tetap dipertahankan.
- Coba `wkwkwk` pada layar sempit dan ukuran teks besar; pasangan tidak menimpa keterangan hasil atau keluar dari panel.
- Letakkan kursor di tengah kata dan tekan tombol `é`; karakter masuk pada posisi kursor dan hasil diperbarui.
- Ganti format huruf; pratinjau teks diproses ikut berubah dan hasil diperbarui.
- Ganti pilihan font; tampilan hasil berubah, dan tombol perkecil tidak ditampilkan.
- Coba spasi, koma, titik, lalu gunakan **Salin hasil** dan **Unduh TXT**.
- Coba tombol ukuran, tema, **Tukar contoh**, dan **Hapus**. Menekan **Terjemahkan** saat input kosong menampilkan pesan.
- Periksa tampilan di layar sempit dan pastikan font yang tersedia merender aksara dengan benar.

## Pengaturan dan easter egg

- Buka ikon roda gigi. Kedua opsi visibilitas tidak dicentang secara default; nyalakan salah satunya dan muat ulang halaman untuk memastikan preferensinya tersimpan.
- Sembunyikan opsi huruf kecil lalu ketik teks kapital: input dan pratinjau tetap mempertahankan huruf asli. Sembunyikan tombol **Terjemahkan**: hasil tetap diperbarui otomatis saat mengetik.
- Tekan **Reset Pengaturan** untuk mengembalikan opsi visibilitas ke keadaan tidak dicentang dan preferensi tampilan lain ke default.
- Di bagian bawah menu Pengaturan, klik **Informasi rahasia** lima kali. Mulai permainan, pilih kartu; pemain menang saat mencapai 7 poin sebelum Asyrafu. **Pentol Hijau** memberi 2 poin dengan aman, sementara kartu lain memberi efek acak atau mencuri poin. Asyrafu mempelajari kartu yang diulang dan memilih counter; mengulang satu kartu bukan strategi kemenangan yang aman.
- Gunakan **Main Lagi** setelah menang atau kalah. Voucher dan restoran sepenuhnya fiktif, tidak dapat ditukarkan, dan permainan tidak memakai taruhan atau mekanik kekerasan.

## Mengganti mesin transliterasi

Fungsi `transliterate` di `script.js` sengaja dipisahkan dari event antarmuka. Untuk mengganti implementasi, pilih pustaka yang secara eksplisit mencakup ortografi Aksara Jawa, periksa lisensi dan versi sumbernya, lalu tambahkan berkas pustaka lokal dan adaptor yang mempertahankan API `transliterate(text)`. Situs ini harus tetap bekerja offline; hindari mengandalkan CDN untuk runtime. Tambahkan contoh uji dari dokumentasi pustaka dan pastikan lisensinya kompatibel sebelum mendistribusikan proyek.