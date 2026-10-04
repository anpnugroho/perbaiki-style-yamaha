# Tool Style Yamaha (PSR-S770) — paket kerja

Folder ini dipakai untuk **menyuntik konten MIDI (rekaman)** ke slot **Ending 1 (Ending A)** dan
**Intro 3 (Intro C)** di file style Yamaha (`.STY`), tanpa mengubah bagian lain.

Prinsip: **baca-tempel dari base**, bukan mengarang. Voice (CC0/CC32/PC), marker, SysEx, chunk
`CASM`, dan `OTSc` selalu disalin utuh dari base. Yang diganti hanya event nada di section target.

## Isi folder

| File | Fungsi |
|---|---|
| `sff.py` | library baca/tulis `.STY` (round-trip byte-identik, sudah diuji) |
| `style_report.py` | laporan cetakan: section, panjang bar, channel/part aktif, voice per section |
| `style_to_mid.py` | export style (seluruhnya atau 1 section) → MIDI standar (buka di DAW) |
| `style_inject.py` | **tool inti**: suntik rekaman MIDI ke section target |
| `analyze_style.py` | bedah cepat 1 style (section timeline + part + voice) |
| `dump_style.py` | dump struktur CASM mentah |
| `parse_datalist_drumkit.py` | tarik peta note drum kit dari PDF Data List Yamaha |
| `studiokit_map.json` | peta note → nama suara **StudioKit** (kick 36, snare 38/40, HH 42/44/46, ...) |
| `samples/` | base style (jangan diubah; anggap readonly) |
| `out/` | hasil export / injeksi |

## Alur pakai (untuk Mas Andre)

```bash
cd scripts/yamaha-style

# 1. lihat cetakan base
python3 style_report.py samples/BASE_LUKA_DISINI_E_V25.STY out/cetakan.md

# 2. export slot jadi template MIDI (track sudah dinamai per part)
python3 style_to_mid.py samples/BASE_LUKA_DISINI_E_V25.STY out/ENDING1_template.mid --section "Ending A"
python3 style_to_mid.py samples/BASE_LUKA_DISINI_E_V25.STY out/INTRO3_template.mid  --section "Intro C"

# 3. (Mas rekam / edit di DAW pakai template itu, simpan sebagai MIDI)

# 4. suntik ke style → hasilkan .STY baru (cek dulu pakai --dry-run)
python3 style_inject.py samples/BASE_LUKA_DISINI_E_V25.STY out/hasil.sty \
    --put "Ending A=rekaman.mid:1-16" \
    --put "Intro C=rekaman.mid:17-44" \
    --dry-run

# 5. kalau sudah OK, jalankan tanpa --dry-run → out/hasil.sty, tinggal copy ke USB → load di S770
```

Opsi tambahan:
- `--time-scale 0.5` → semua posisi tick × 0.5 (rekaman jadi 2× lebih cepat; dipakai kalau rekaman pop/asal lebih lambat)
- `--map "1:8,2:9,3:10"` → map channel MIDI masukan → channel style (kalau hasil rekaman pakai channel berbeda)
- `--import-cc` → ikut mengimpor CC (volume/expression dsb) dari rekaman; default: CC tetap pakai base

## Batasan yang sudah diketahui

- Panjang section **tidak berubah** (diambil dari base). Kalau rekaman lebih panjang dari slot, kelebihannya dibuang + diberi peringatan.
- CASM tidak disentuh → aturan follow-chord mengikuti base (sesuai kebutuhan: intro/interlude ikut akor).
- Voice tidak diubah → part akan berbunyi dengan sound yang sama seperti base.
- `SInt` (marker 1 bar di awal) belum kita sentuh; belum jelas dipakai untuk apa di S770.

## Hasil uji

- Round-trip: baca → tulis ulang = **md5 identik** (2 file base berbeda).
- Self-test injeksi: `Ending A` diekspor ke MIDI lalu disuntik balik → **jumlah note per channel identik**,
  section lain tidak berubah, chunk CASM identik.

---

## Fitur baru: "Perbaiki Style" (perbaiki_style/)

UI lokal untuk membetulkan style: **browse file .STY** → part **Main A–D, Fill In A–D, Break,
Ending 2, Ending 3** diganti supaya persis seperti **style template** yang sudah diprogram.

Jalan tanpa dependency (Python 3 stdlib):

```bash
cd perbaiki_style
python3 app.py            # buka http://127.0.0.1:3210
```

- Template default: taruh di `perbaiki_style/templates/template.STY`
  (atau unggah template langsung di UI, untuk sekali proses).
- Nama section yang dicari per part ada di `perbaiki_style/parts_map.json` (bisa diubah tanpa ubah kode).
- Yang **tidak** diubah: chunk CASM/OTSc, marker section, tempo, voice (CC0/CC32/PC), dan part lain.
- Mode `fit`: panjang section mengikuti **style target**. Kalau konten template lebih panjang, kelebihannya dipotong dan nada yang terpotong otomatis ditutup (biar tidak ada nada nyangkut).
- Hasil tersimpan di `perbaiki_style/out/` + otomatis terunduh dari browser.
- Template terpasang: `4KU C4H KERJO A DC V23` (SFF2). Section di file ini: Main A–D, Fill In AA/BB/CC/DD, **Fill In BA** (= dipakai untuk "Break", karena tidak ada section bernama `Break`), Ending B (=Ending 2, 8 bar), Ending C (=Ending 3, 5 bar).

CLI (tanpa UI):

```bash
cd perbaiki_style
python3 repair.py TARGET.STY TEMPLATE.STY OUT.STY                # semua part
python3 repair.py TARGET.STY TEMPLATE.STY OUT.STY main_a,fill_a  # part tertentu
```

### Pembaruan 3/10/2026 — channel/CASM per section

- Setiap style menyimpan **channel per part** di blok CASM (tiap style bisa beda, mis. Rhythm2
  di template ada di ch8 sedangkan style lain memakainya di ch6). Kalau hanya note yang disalin,
  part itu bisa **tidak bunyi**.
- Karena itu "Perbaiki Style" sekarang **ikut menyalin konfigurasi CASM section dari template**
  (channel + voice + aturan chord) untuk part yang diganti → hasilnya benar-benar seperti template.
  Kalau nama section di template berbeda (mis. target `Fill In BA` ← template `Break`), sistem
  otomatis jatuh ke mode aman: **remap channel berdasarkan nama part** milik style target.
- **Template campuran**: part tertentu bisa diambil dari file lain lewat `templates/sources.json`:
  ```json
  { "main_d": "NEGORO84M3_4NGIN_D_V23.STY",
    "fill_d": "NEGORO84M3_4NGIN_D_V23.STY",
    "ending_2": "NEGORO84M3_4NGIN_D_V23.STY" }
  ```
  (file-file donor ditaruh di folder `templates/`).

### Pembaruan 3/10/2026 (2) — opsi panjang part

- Pilihan **"Panjang part"** di UI:
  - **utuh seperti template** (`grow`, default) — kalau part di template lebih panjang, section di style ikut
    **dilebarkan** sebesar selisihnya; isi section setelahnya digeser, jadi part tetap utuh
    (contoh: Ending 3 target 4 bar + template 5 bar → hasil 5 bar penuh).
  - **potong ikut style** (`fit`) — konten template dipotong mengikuti panjang section style target.
- Section/part lain yang tidak dipilih **tidak berubah** (isi & panjangnya tetap).

### Pembaruan 3/10/2026 (3) — nama file hasil

- Hasil **disimpan & diunduh dengan nama yang sama seperti file sumber** (spasi, `@`, `&`, dst
  dipertahankan; extension asli seperti `.S801` ikut) — tidak ada lagi tambahan `_FIX_tanggal`
  yang memaksa rename.
- Backup tetap jalan otomatis tanpa memperlambat: hasil terakhir di `out/<nama asli>`,
  arsip ber-timestamp di `out/arsip/<YYYYmmdd-HHMMSS>__<nama asli>`.
- Yang tidak boleh hanya pemisah folder (`/`, `\`) dan karakter kontrol — itu dibuang otomatis.

### Pembaruan 3/10/2026 (4) — template bisa diganti-ganti dari UI

- **Template default**: `templates/Template V23.STY`. Nama ini tampil di UI.
- Kalau di folder `templates/` ada **lebih dari satu** file template, muncul **dropdown "Template utama"**
  untuk memilih; kalau hanya satu, UI cuma menampilkan nama template aktif (tidak ada dropdown).
- File yang dipakai sebagai **donor per-part** (`templates/sources.json`) **disembunyikan** dari daftar
  supaya tidak bingung — dia tetap dipakai untuk part yang terdaftar.
- Masih bisa **unggah template lain** untuk satu kali proses (mengalahkan template aktif).

### Pembaruan 4/10/2026 — fitur BARU (opsional): rapikan Intro 1–3 & Ending 1

Di UI ada checkbox baru **“rapikan Intro 1–3 & Ending 1 (bass/rhythm)”** (di baris “pilih semua”).
Kalau dicentang, setelah proses *replace* biasa selesai, tool otomatis merapikan section
**Intro A / Intro B / Intro C** dan **Ending A**:

- **Bass** — kit/voice (MSB/LSB/PC) disamakan dengan **Bass Main A**; lalu filter & EQ di-reset:
  Harmonic Content → 0, Brightness → 0, EQ High → 0, EQ Low → +20.
  (Angka keyboard “0 / +20” = nilai SysEx **64 / 84**. Harmonic Content = **CC71**, Brightness = **CC74**,
  EQ = SysEx XG `08 <ch> 73` (high) & `08 <ch> 72` (low).)
- **Rhythm1** — kit disamakan dengan **Rhythm1 Fill In A**.
- **Rhythm2** — kit disamakan dengan **Rhythm2 Main A**.

Catatan teknis:
- **Fitur lama tidak diubah** — tanpa centang, hasil persis seperti sebelumnya (sudah diverifikasi byte-identik).
- Voice diset lewat CC0/CC32/PC + SysEx, ditempel **tepat setelah marker section** agar tetap dianggap bagian section itu.
- Part yang tidak ada di section target/referensi dilewati dan dilaporkan di UI.
- Implementasi: `repair.fix_intro_ending(bytes, ...)` di `repair.py` — fungsi terpisah dari `repair()`.

#### Perbaikan (4/10/2026, lanjutan) — part tanpa nama di CASM

Di sebagian style, record CASM part bass di Intro/Ending **namanya kosong** (baru channel-nya
yang terisi). Versi awal fitur cuma mengenali part lewat namanya, jadi bass di section itu
terlewat. Sekarang tool membaca **semua** record CASM (termasuk yang kosong) dan menyimpulkan
part-nya dari **channel referensi** (Bass = channel Bass Main A, dst), dengan pengaman: channel
yang sudah dipakai part lain yang bernama tidak disentuh.

#### Donor khusus part Bass (4/10/2026)

`perbaiki_style/templates/sources.json` sekarang bisa menunjuk donor berbeda untuk **part Bass**
saja — jadi mis. **Ending 2** bisa ambil bass dari **Template V23** sementara part lain tetap
dari **NEGORO**:

```json
{
  "main_d": "NEGORO84M3_4NGIN_D_V23.STY",
  "fill_d": "NEGORO84M3_4NGIN_D_V23.STY",
  "ending_2": { "file": "NEGORO84M3_4NGIN_D_V23.STY", "bass": "Template V23.STY" }
}
```

Yang diambil dari donor bass: **kit (CC0/CC32/PC)** + **filter (CC71/CC74)** + **EQ (XG 8-x-72/73)**.
Not/garis bass tetap dari donor utama (`file`).
