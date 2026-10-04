# templates/

## Template utama
Taruh style template di folder ini. Yang dipakai sebagai **template default**:

```
Template V23.STY
```

File lain di folder ini otomatis muncul sebagai pilihan **hanya kalau jumlahnya lebih dari satu**
(kalau cuma satu, UI menampilkan nama template aktif saja).

## Part khusus dari file lain
Part tertentu bisa diambil dari file lain lewat `sources.json`:

```json
{
  "main_d":   "NAMA-FILE-LAIN.STY",
  "fill_d":   "NAMA-FILE-LAIN.STY",
  "ending_2": "NAMA-FILE-LAIN.STY"
}
```

File donor ini **tidak muncul** di daftar template (supaya tidak membingungkan) — dia hanya
dipakai untuk part yang tercatat di atas.

Part yang didukung: `main_a`…`main_d`, `fill_a`…`fill_d`, `break`, `ending_2`, `ending_3`.
Nama section yang dicari per part ada di `../parts_map.json`.
