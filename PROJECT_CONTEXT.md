# PROJECT: Tool Style Yamaha (PSR-S770) — Injector Intro/Interlude

**Status:** tool inti SELESAI & teruji · menunggu Mas Andre rekam MIDI
**Terakhir diperbarui:** 2026-09-15 18:40 WIB

## Tujuan
Membantu Mas Andre (keyboardist, Yamaha **PSR-S770**) membuat **style dangdut** dengan cara
mengganti **hanya 2 slot** pada style base:
- **Intro lagu → Ending 1** (marker di file: `Ending A`)
- **Interlude → Intro 3** (marker di file: `Intro C`)

Main A/B/C/D, Ending 2/3, Fill → tinggal copy/persis dari base (tidak diutak-atik).

## Aturan dari Mas (final, 15/9)
1. **Voice**: "yang penting sama saja" → tool hanya **menyalin** blok CC0/CC32/PC dari base (tidak perlu daftar nama voice).
2. **OTS (`OTSc`)**: dipertahankan apa adanya — tidak disentuh.
3. **Rhythm 1**: pattern-nya selalu itu, **dipanjangkan mengikuti jumlah bar** section (Ending A / Intro C).
4. **Intro & interlude mengikuti akor** (bukan fix) — base contoh juga sudah follow-chord → cukup salin perilaku CASM dari base.
5. **Sumber konten**: belum ada MIDI dangdut; Mas akan **rekam sendiri** kalau sempat. Stok MIDI-nya umumnya pop (tempo ± setengah dangdut → perlu `--time-scale`).
6. Tidak perlu reference style tambahan — acuan = base style itu sendiri.

## Base style
- **Benar:** `scripts/yamaha-style/samples/BASE_LUKA_DISINI_E_V25.STY` — 109 KB, **135 BPM**, chunk: `MThd, MTrk, CASM, OTSc`
- Sudah-salah (versi lama, disimpan sebagai sample): `BASE_KESAYANGAN_A_V23.STY` — 125 BPM, Ending A 34 bar
- Format: SMF format 0, 1 track, division **1920** → **1 bar 4/4 = 7680 tick**
- Section pada base (nama marker → slot keyboard → panjang):
  `SInt` 1 bar · `Main A–D` 16 bar · `Fill In AA–DD` 1 bar · **`Intro C` 28 bar (Intro 3)** · `Intro A` 32 bar · `Ending B` 3 · `Ending C` 4 · **`Ending A` 16 bar (Ending 1)** · `Fill In BA` 1 bar
  ⚠️ Panjang section **ikut lagu** (base lama: Intro C 18 / Ending A 34) — bukan angka patok.
- Channel/part (1-based): ch9 Rhythm1 · **ch10 Rhythm2 = StudioKit** · ch11 Bass · ch12 Chord1 · ch13 Chord2 · ch14 Pad · ch15 Phrase1 · ch16 Phrase2. Ada channel tambahan **ch8** (drum kit lain, 127-0-4) yang aktif di slot target — **belum dikonfirmasi Mas apa namanya**.
- Voice di-set **per section** (contoh Rhythm2: `SInt` = 62-0-57, dari `Main D` dst = 127-0-86 = StudioKit).
- **StudioKit** = MSB 127 / LSB 0 / PC 86 (0-based; di Data List tertulis 127-0-87 karena PC dihitung 1–128).
- Peta note StudioKit tersimpan: `scripts/yamaha-style/studiokit_map.json` (kick 36, snare 38/40, HH 42/44/46, tom 41–50, crash 49/57, ride 51/59, dst.) — hasil tarik dari PDF Data List PSR-S970/S770 hal. 29 kolom ke-3, dan sudah diverifikasi silang dengan pemakaian nyata di style Mas.

## Tool (folder `~/.openclaw/workspace/scripts/yamaha-style/`)
| File | Fungsi |
|---|---|
| `sff.py` | library baca/tulis `.STY` (events disimpan sebagai (tick, raw) agar aman ditulis ulang) |
| `style_report.py` | laporan "cetakan": section, bar, part/channel aktif, voice per section |
| `style_to_mid.py` | export style / 1 section → MIDI standar (SMF type 1, track per part) |
| `style_inject.py` | **INTI** — suntik MIDI ke slot section (opsi `--time-scale`, `--map`, `--import-cc`, `--dry-run`) |
| `analyze_style.py`, `dump_style.py` | bedah cepat / dump CASM mentah |
| `parse_datalist_drumkit.py` | tarik kolom drum kit dari PDF Data List |
| `samples/`, `out/`, `README.md` | data base, hasil, dokumentasi pakai |

### Cara pakai (untuk Mas)
```bash
cd ~/.openclaw/workspace/scripts/yamaha-style
python3 style_to_mid.py samples/BASE_LUKA_DISINI_E_V25.STY out/TEMPLATE_ENDING1_16bar.mid --section "Ending A"
python3 style_to_mid.py samples/BASE_LUKA_DISINI_E_V25.STY out/TEMPLATE_INTRO3_28bar.mid  --section "Intro C"
# rekam di DAW pakai template itu, lalu:
python3 style_inject.py samples/BASE_LUKA_DISINI_E_V25.STY out/hasil.sty \
    --put "Ending 1=rekaman.mid:1-16" --put "Intro 3=rekaman.mid:17-44"
# → copy .sty ke USB → load di PSR-S770
```

## Bukti uji (jangan dihapus)
- **Round-trip**: baca → tulis ulang `.STY` = **md5 identik** (dua base berbeda). Chunk CASM/OTSc identik.
- **Self-test injeksi**: `Ending A` diekspor ke MIDI → disuntik balik → **jumlah note per channel identik**, section lain tidak berubah, CASM identik, total event sama (20496).

## Pertanyaan terbuka
1. **ch8** (kit 127-0-4) di slot target — itu yang Mas sebut "Rhythm 1"? Kalau ya & harus diisi juga, perlu fitur **"salin pola Rhythm1 dari section lain + stretch ke panjang slot"**.
2. Setelah Mas rekam: format rekaman (MIDI dari DAW / hasil Style Creator) untuk memastikan mapping channel.

## Langkah berikutnya
1. Mas rekam intro (16 bar) & interlude (28 bar) → kirim `.mid`
2. Aku jalankan `style_inject.py` → hasil `.sty` → tes di keyboard
3. Kalau perlu: tambah fitur stretch Rhythm1, dan/atau pipeline "pop MIDI → dangdut" (melodi dari pop + irama dari library Mas)
