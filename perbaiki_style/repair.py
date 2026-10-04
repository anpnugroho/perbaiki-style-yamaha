#!/usr/bin/env python3
"""repair.py — mesin fitur "Perbaiki Style".

Inti: ambil konten part tertentu dari sebuah **style template** (yang sudah diprogram),
lalu tempel ke style yang dipilih — supaya part-part itu persis seperti template.

Part yang ditangani (lihat parts_map.json):
  Main A–D · Fill In A–D · Break · Ending 2 · Ending 3

Yang TIDAK diubah: chunk MThd/CASM/OTSc, marker section, tempo, voice (CC0/CC32/PC),
dan seluruh part lain di luar daftar target.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sff  # noqa: E402
import casm  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(HERE, "templates")
NOTE_ON_MASK = 0x90


def load_parts_map():
    with open(os.path.join(HERE, "parts_map.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _sources_raw():
    path = os.path.join(TEMPLATES_DIR, "sources.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_sources():
    """templates/sources.json -> {id_part: nama_file} untuk donor khusus per part.

    Nilai boleh nama file (string) atau objek {"file": ..., "bass": ...}; kunci "bass"
    = donor khusus untuk part Bass saja (mis. Ending 2: bass dari Template V23,
    sisanya tetap dari NEGORO).
    """
    out = {}
    for key, val in _sources_raw().items():
        name = val.get("file") if isinstance(val, dict) else val
        if name:
            out[key] = name
    return out


def load_bass_sources():
    """Donor khusus part Bass -> {id_part: nama_file}."""
    return {k: v["bass"] for k, v in _sources_raw().items()
            if isinstance(v, dict) and v.get("bass")}


def source_file(part_id):
    """Path file donor untuk part tertentu (None = pakai template utama)."""
    name = load_sources().get(part_id)
    if not name:
        return None
    path = os.path.join(TEMPLATES_DIR, name)
    return path if os.path.isfile(path) else None


def find_section(style, part):
    """Cari section di style berdasarkan nama utama + alias (case-insensitive)."""
    wanted = [part.get("section")] + list(part.get("aliases") or [])
    by_name = {s["name"].strip().lower(): s for s in style.sections()}
    for name in wanted:
        if not name:
            continue
        sec = by_name.get(str(name).strip().lower())
        if sec:
            return sec
    return None


def section_notes(style, sec):
    if not sec:
        return 0
    n = 0
    for tick, raw in style.events:
        if sec["start"] <= tick < sec["end"] and (raw[0] & 0xF0) == NOTE_ON_MASK and len(raw) > 2 and raw[2] > 0:
            n += 1
    return n


def analyze(style_bytes, parts_map=None):
    """Info style + status tiap part target."""
    style = sff.Style(data=style_bytes)
    pm = parts_map or load_parts_map()
    yamaha_tempo = style.tempo

    parts = []
    for p in pm:
        sec = find_section(style, p)
        parts.append({
            "id": p["id"],
            "label": p["label"],
            "section": p.get("section"),
            "found": bool(sec),
            "section_name": sec["name"] if sec else None,
            "bars": round(sec["bars"], 2) if sec else None,
            "notes": section_notes(style, sec),
        })

    return {
        "style": {
            "division": style.division,
            "bar_ticks": style.bar_ticks,
            "tempo": yamaha_tempo,
            "chunks": [c[0].decode("latin1") for c in style.chunks],
        },
        "sections": [{"name": s["name"], "bars": round(s["bars"], 2)} for s in style.sections()],
        "parts": parts,
    }


def _events_relative(style, sec):
    base = sec["start"]
    out = []
    for tick, raw in style.events:
        if sec["start"] <= tick < sec["end"]:
            out.append((tick - base, raw))
    return out


def _close_hanging_notes(events, span):
    """Tutup note yang terpotong di akhir section supaya tidak ada nada nyangkut."""
    active = {}
    for tick, raw in events:
        hi = raw[0] & 0xF0
        if hi == NOTE_ON_MASK and len(raw) > 2:
            key = (raw[0] & 0x0F, raw[1])
            if raw[2] > 0:
                active[key] = tick
            else:
                active.pop(key, None)
    extra = []
    for (ch, note), start in active.items():
        end = min(span - 1, max(start + 1, span - 1))
        extra.append((end, bytes([NOTE_ON_MASK | ch, note, 0])))
    return sorted(events + extra, key=lambda e: e[0])


def repair(style_bytes, template_bytes, part_ids=None, mode="fit", overrides=None, bass_overrides=None):
    """
    style_bytes   : style yang diperbaiki
    template_bytes: style sumber utama (berisi part yang sudah diprogram)
    part_ids      : daftar id part yang diganti (None = semua dari parts_map)
    mode          : saat ini hanya "fit" -> panjang section mengikuti style target
                    (konten template yang lebih panjang dipotong, nada dipotong ditutup otomatis)
    overrides     : {id_part: bytes_style} untuk donor khusus per part (template campuran)
    bass_overrides: {id_part: bytes_style} donor khusus part Bass (kit+filter+EQ diambil dari
                    sini; not/garis bass tetap dari donor utama)
    """
    if mode not in ("fit", "grow"):
        raise ValueError('mode "%s" belum didukung (pakai "fit" atau "grow")' % mode)

    target = sff.Style(data=style_bytes)
    tpl_cache = {}

    def get_donor(blob):
        key = id(blob)
        if key not in tpl_cache:
            tpl_cache[key] = sff.Style(data=blob)
        return tpl_cache[key]

    pm = load_parts_map()
    ids = set(part_ids) if part_ids else {p["id"] for p in pm}

    target_casm = casm.load(target)
    target_sections = target.sections()
    casm_updates = []  # [(bytes_casm_donor, {nama_section})]
    report = []

    # Kerjakan urut posisi section: mode "grow" menggeser section berikutnya,
    # jadi urutan penting supaya posisi tiap section tetap dihitung ulang dengan benar.
    todo = [p for p in pm if p["id"] in ids]
    todo.sort(key=lambda p: (find_section(target, p) or {"start": 10 ** 9})["start"])

    for p in todo:
        t_sec = find_section(target, p)  # dihitung segar tiap part (section bisa bergeser)

        donor_blob = (overrides or {}).get(p["id"]) or template_bytes
        donor = get_donor(donor_blob)
        donor_casm = casm.load(donor)

        d_sec = find_section(donor, p)
        row = {"id": p["id"], "label": p["label"], "status": "ok",
               "target_section": t_sec["name"] if t_sec else None,
               "template_section": d_sec["name"] if d_sec else None,
               "target_bars": round(t_sec["bars"], 2) if t_sec else None,
               "template_bars": round(d_sec["bars"], 2) if d_sec else None,
               "notes_in": 0, "truncated": False, "grown_bars": 0, "remap": [], "casm": "-"}

        if not t_sec:
            row["status"] = "target_tidak_ada"
            report.append(row)
            continue
        if not d_sec:
            row["status"] = "template_tidak_ada"
            report.append(row)
            continue

        # Cara paling setia: pakai juga konfigurasi CASM section dari template
        # (channel + voice + aturan chord) sehingga hasilnya benar-benar seperti template.
        donor_parts = donor_casm.get(d_sec["name"], [])
        target_parts = target_casm.get(t_sec["name"], [])
        remap = {}
        if (d_sec["name"] == t_sec["name"] and donor_casm.get(d_sec["name"])
                and target_casm.get(t_sec["name"])):
            donor_casm_bytes = [pl for n, pl in donor.chunks if n == b"CASM"]
            if donor_casm_bytes:
                casm_updates.append((donor_casm_bytes[0], {t_sec["name"]}))
                row["casm"] = "template"
        else:
            # Fallback: pindahkan channel sesuai nama part milik style ini.
            remap = casm.build_remap(donor_parts, target_parts)
            row["remap"] = [f"ch{a + 1}->ch{b + 1}" for a, b in sorted(remap.items()) if a != b]
            row["casm"] = "remap" if remap else "-"

        donated = _events_relative(donor, d_sec)
        span = t_sec["end"] - t_sec["start"]
        donor_span = d_sec["end"] - d_sec["start"]

        # Mode "grow": ikut panjang template -> section target dilebarkan,
        # isi setelahnya digeser sebesar selisihnya (struktur lain tidak berubah).
        if mode == "grow" and donor_span > span:
            delta = donor_span - span
            target.events = sorted(
                [((t + delta), raw) if t >= t_sec["end"] else (t, raw) for t, raw in target.events],
                key=lambda e: e[0]
            )
            t_sec = dict(t_sec, end=t_sec["end"] + delta,
                         bars=round((t_sec["end"] + delta - t_sec["start"]) / target.bar_ticks, 3))
            span = donor_span
            row["grown_bars"] = round(delta / target.bar_ticks, 2)
            row["target_bars"] = t_sec["bars"]

        # Volume (CC7) & expression (CC11) asli style target per channel. Dipakai untuk
        # menambal part yang tidak disetel volume-nya oleh template: kalau dibiarkan,
        # keyboard memakai default (127) sehingga part itu jadi terlalu keras.
        tgt_cc = {}
        for tick, raw in target.events:
            if t_sec["start"] <= tick < t_sec["end"] and (raw[0] & 0xF0) == 0xB0 and raw[1] in (7, 11):
                tgt_cc.setdefault((raw[0] & 0x0F, raw[1]), raw[2])

        kept = []
        for tick, raw in target.events:
            inside = t_sec["start"] <= tick < t_sec["end"]
            is_eot = raw[0] == sff.META and raw[1] == sff.EOT
            if inside and not is_eot:
                continue
            kept.append((tick, raw))

        added = []
        for rel, raw in donated:
            if raw[0] == sff.META and raw[1] == sff.EOT:
                continue
            if mode == "fit" and rel >= span:
                row["truncated"] = True
                continue
            added.append((t_sec["start"] + rel, casm.remap_event(raw, remap)))

        if row["truncated"]:
            added = _close_hanging_notes(added, t_sec["end"])

        # Donor khusus part Bass: ambil KIT (CC0/CC32/PC) + FILTER (CC71/CC74) + EQ (XG 72/73)
        # dari donor lain. Not/garis bass tetap dari donor utama.
        if (bass_overrides or {}).get(p["id"]):
            b_style = get_donor(bass_overrides[p["id"]])
            added, bch = _override_bass_setup(added, donor_parts, remap, row["casm"],
                                              b_style, find_section(b_style, p), t_sec["start"])
            if bch is not None:
                row["bass_from"] = load_bass_sources().get(p["id"], "?")

        # Tambal volume/expression part yang tidak disediakan template (cegah lompat ke 127).
        have = set()
        for _t, raw in added:
            if (raw[0] & 0xF0) == 0xB0 and raw[1] in (7, 11):
                have.add((raw[0] & 0x0F, raw[1]))

        final_parts = donor_parts if row["casm"] == "template" else [(n, remap.get(ch, ch)) for n, ch in donor_parts]
        # Cocokkan part target <-> part hasil lewat NAMA part (bisa ada nama kembar,
        # mis. 2x Rhythm1 / 2x Pad -> pasangkan menurut urutan). Fallback: channel sama.
        by_name = {}
        for n, ch in final_parts:
            by_name.setdefault(n, []).append(ch)
        tgt_by_name = {}
        for n, ch in target_parts:
            tgt_by_name.setdefault(n, []).append(ch)

        filled = 0
        for pname, tchs in tgt_by_name.items():
            fchs = by_name.get(pname, tchs)
            for i, tch in enumerate(tchs):
                fch = fchs[i] if i < len(fchs) else tch
                for cc in (7, 11):
                    if (tch, cc) in tgt_cc and (fch, cc) not in have:
                        added.append((t_sec["start"], bytes([0xB0 | fch, cc, tgt_cc[(tch, cc)]])))
                        have.add((fch, cc))
                        filled += 1
        row["volume_filled"] = filled

        target.events = sorted(kept + added, key=lambda e: e[0])
        row["notes_in"] = sum(1 for _, raw in added if (raw[0] & 0xF0) == NOTE_ON_MASK and len(raw) > 2 and raw[2] > 0)
        report.append(row)

    # Tulis ulang CASM dengan konfigurasi section dari template (kalau ada).
    if casm_updates:
        cur = [p for n, p in target.chunks if n == b"CASM"]
        if cur:
            new_casm = cur[0]
            for donor_casm_bytes, names in casm_updates:
                new_casm, _ = casm.replace_sections(new_casm, donor_casm_bytes, names)
            for i, (n, _p) in enumerate(target.chunks):
                if n == b"CASM":
                    target.chunks[i][1] = new_casm

    out = bytearray()
    target.chunks[target.track_index][1] = sff.build_track(target.events)
    for name, payload in target.chunks:
        out += name + len(payload).to_bytes(4, "big") + payload

    return bytes(out), {"mode": mode, "parts": report, "target_sections": [s["name"] for s in target_sections]}


# =====================================================================
# FITUR BARU (terpisah dari repair()): rapikan Intro 1-3 & Ending 1.
#
#   Bass    : kit/voice (CC0/CC32/PC) disamakan dengan Bass Main A,
#             filter harmonic content & brightness -> 0, EQ high -> 0, EQ low -> +20.
#             (nilai XG: keyboard menampilkan nilai-64, jadi 0 -> 64 dan +20 -> 84)
#   Rhythm1 : kit/voice disamakan dengan Rhythm1 Fill In A.
#   Rhythm2 : kit/voice disamakan dengan Rhythm2 Main A.
#
# Dipakai SETELAH repair(), supaya Main A / Fill In A sudah versi template.
# =====================================================================
INTRO_ENDING_SECTIONS = ("Intro A", "Intro B", "Intro C", "Ending A")
PART_REF_SECTION = {"Bass": "Main A", "Rhythm1": "Fill In AA", "Rhythm2": "Main A"}
VOICE_PARTS = ("Bass", "Rhythm1", "Rhythm2")
BASS_CC_SET = {71: 64, 74: 64}      # Harmonic Content, Brightness (0)
BASS_XG_SET = {0x73: 64, 0x72: 84}  # EQ High (0), EQ Low (+20)


def _xg_part(channel, addr_low, value):
    """SysEx XG parameter change: 08 <channel> <addr_low> <value>."""
    return bytes([0xF0, 0x08, 0x43, 0x10, 0x4C, 0x08, channel, addr_low, value, 0xF7])


_BASS_SETUP_ORDER = [("cc", 0), ("cc", 32), ("pc",), ("cc", 71), ("cc", 74), ("sx", 0x73), ("sx", 0x72)]


def _bass_setup_events(style, section, channel):
    """Setup part bass di section/channel: kit CC0/CC32/PC + filter CC71/CC74 + EQ XG 72/73."""
    found = {}
    for t, raw in style.events:
        if not (section["start"] <= t < section["end"]):
            continue
        b = bytes(raw)
        if b[0] == 0xF0:
            if len(b) >= 10 and b[2:5] == b"\x43\x10\x4c" and b[6] == channel and b[7] in (0x72, 0x73):
                found.setdefault(("sx", b[7]), b)
            continue
        if b[0] >= 0xF0 or (b[0] & 0x0F) != channel:
            continue
        kind = b[0] & 0xF0
        if kind == 0xB0 and b[1] in (0, 32, 71, 74):
            found.setdefault(("cc", b[1]), b)
        elif kind == 0xC0:
            found.setdefault(("pc",), b)
    return found


def _override_bass_setup(added, donor_parts, remap, casm_mode, bass_style, bass_section, start):
    """Ganti setup part bass di `added` dengan milik donor lain. -> (added, channel|None)"""
    if bass_section is None:
        return added, None
    pairs = donor_parts if casm_mode == "template" else [(nm, remap.get(ch, ch)) for nm, ch in donor_parts]
    fch = next((ch for nm, ch in pairs if nm == "Bass"), None)
    if fch is None:
        return added, None
    sch = next((ch for ch, nm in _casm_parts_all(bass_style).get(bass_section["name"], []) if nm == "Bass"), None)
    if sch is None:
        return added, None
    want = _bass_setup_events(bass_style, bass_section, sch)
    new = []
    for key in _BASS_SETUP_ORDER:
        raw = want.get(key)
        if raw is None:
            continue
        if key[0] == "sx":
            new.append(_xg_part(fch, key[1], raw[8]))
        elif key[0] == "pc":
            new.append(bytes([0xC0 | fch, raw[1]]))
        else:
            new.append(bytes([0xB0 | fch, key[1], raw[2]]))
    if not new:
        return added, None

    def is_bass_setup(raw):
        b = bytes(raw)
        if b[0] == 0xF0:
            return len(b) >= 10 and b[2:5] == b"\x43\x10\x4c" and b[6] == fch and b[7] in (0x72, 0x73)
        if b[0] >= 0xF0 or (b[0] & 0x0F) != fch:
            return False
        kind = b[0] & 0xF0
        return (kind == 0xB0 and b[1] in (0, 32, 71, 74)) or kind == 0xC0

    out = [(start, raw) for raw in new]
    out += [(t, raw) for t, raw in added if not is_bass_setup(raw)]
    return out, fch


def _first_voice(style, section, channel):
    """Nilai voice (CC0/CC32/PC) pertama di section untuk channel tertentu."""
    msb = lsb = pc = None
    for t, raw in style.events:
        if not (section["start"] <= t < section["end"]) or (raw[0] & 0x0F) != channel or raw[0] >= 0xF0:
            continue
        kind = raw[0] & 0xF0
        if kind == 0xB0:
            if raw[1] == 0 and msb is None:
                msb = raw[2]
            elif raw[1] == 32 and lsb is None:
                lsb = raw[2]
        elif kind == 0xC0 and pc is None:
            pc = raw[1]
    return msb, lsb, pc


def _name_candidates(name):
    """Part yang mungkin untuk nama record yang tidak standar ('' / 'Rhytm' / 'Rhy1')."""
    if not name:
        return set(VOICE_PARTS)
    if name.lower().startswith("rhy"):
        return {"Rhythm1", "Rhythm2"}
    return set()


def _part_ok(style, section, channel, part, want):
    """True kalau setelan part di section sudah persis sesuai target (tidak perlu diubah)."""
    if None in want:
        return False
    if tuple(_first_voice(style, section, channel)) != tuple(want):
        return False
    n_msb = n_pc = 0
    ccs = {}
    sx = {}
    for t, raw in style.events:
        if not (section["start"] <= t < section["end"]):
            continue
        if raw[0] == 0xF0:
            b = bytes(raw)
            if len(b) >= 10 and b[2:5] == b"\x43\x10\x4c" and b[6] == channel:
                sx["%02x" % b[7]] = b[8]
            continue
        if (raw[0] & 0x0F) != channel:
            continue
        kind = raw[0] & 0xF0
        if kind == 0xB0:
            if raw[1] == 0:
                n_msb += 1
            elif raw[1] in BASS_CC_SET:
                ccs[raw[1]] = raw[2]
        elif kind == 0xC0:
            n_pc += 1
    if n_msb != 1 or n_pc != 1:
        return False
    if part == "Bass":
        if any(ccs.get(cc) != val for cc, val in BASS_CC_SET.items()):
            return False
        if any(sx.get("%02x" % a) != val for a, val in BASS_XG_SET.items()):
            return False
    return True


def _casm_parts_all(style):
    """{section: [(channel, nama_part|None), ...]} — termasuk record yang namanya KOSONG.

    Di beberapa style, part bass/rhythm di Intro/Ending belum diberi nama di CASM
    (record-nya kosong), jadi harus disimpulkan dari channel referensi.
    """
    out = {}
    for cname, payload in style.chunks:
        if cname != b"CASM":
            continue
        for sname, cseg in casm.sections_raw(payload):
            recs = []
            for chunk in cseg[casm.header_len(cseg):].split(b"Ctb2"):
                data = chunk[4:]
                if len(data) < 9:
                    continue
                nm = data[1:9].decode("latin1").strip()
                recs.append((data[0], nm or None))
            out[sname] = recs
    return out


def fix_intro_ending(style_bytes, section_names=None, logger=None):
    """Tambahkan perbaikan Bass/Rhythm1/Rhythm2 pada Intro 1-3 & Ending 1.

    Referensi kit diambil dari section yang sudah diperbaiki (Main A / Fill In A).
    Mengembalikan (bytes_baru, report).
    """
    tgt = sff.Style(data=style_bytes)
    secs = {s["name"]: s for s in tgt.sections()}
    names = list(section_names or INTRO_ENDING_SECTIONS)

    # 1) Channel referensi + nilai kit per part (cari record yang namanya cocok).
    allparts = _casm_parts_all(tgt)
    ref = {}
    ref_ch = {}
    for part, refname in PART_REF_SECTION.items():
        rsec = secs.get(refname)
        rch = next((ch for ch, nm in allparts.get(refname, []) if nm == part), None)
        if rsec is not None and rch is not None:
            ref_ch[part] = rch
            ref[part] = _first_voice(tgt, rsec, rch)

    # Peta channel -> part dari record yang namanya dikenali. Dipakai kalau nama
    # record tidak standar (mis. "Rhytm") atau kosong. Hanya dipakai kalau suaranya bulat.
    votes = {}
    for _sn, recs in allparts.items():
        for ch, nm in recs:
            if nm in VOICE_PARTS:
                votes.setdefault(ch, {})
                votes[ch][nm] = votes[ch].get(nm, 0) + 1
    chan_part = {}
    for ch, v in votes.items():
        best = sorted(v.items(), key=lambda kv: -kv[1])
        if len(best) == 1 or best[0][1] > best[1][1]:
            chan_part[ch] = best[0][0]

    # 2) Channel target per section. Part tanpa nama standar disimpulkan dari channel
    #    (dari section lain di style yang sama), fallback ke channel referensi part itu.
    active = {}
    targets = {}
    rows = []
    for sn in names:
        sec = secs.get(sn)
        if sec is None:
            rows.append({"section": sn, "status": "section tidak ada"})
            continue
        named = {}
        unknown = []
        blank = set()
        for ch, nm in allparts.get(sn, []):
            if nm in VOICE_PARTS:
                named.setdefault(nm, []).append(ch)
            else:
                unknown.append((ch, nm))
                if not nm:
                    blank.add(ch)
        row = {"section": sn, "parts": []}
        tgt_ch = {}
        for part in VOICE_PARTS:
            chans = list(named.get(part, []))
            if not chans:
                # Nama tidak standar/kosong: hanya percaya kalau channel itu memang
                # milik part tsb di section lain (dan namanya masih masuk akal).
                chans = [ch for ch, nm in unknown
                         if part in _name_candidates(nm) and chan_part.get(ch) == part]
            if not chans and part in ref_ch and ref_ch[part] in blank:
                chans = [ref_ch[part]]
            if not chans or part not in ref:
                row["parts"].append({"part": part, "status": "part tidak ada" if not chans else "referensi tidak ada"})
                continue
            todo = [ch for ch in chans if not _part_ok(tgt, sec, ch, part, ref[part])]
            if todo:
                tgt_ch[part] = todo
            old = _first_voice(tgt, sec, chans[0])
            row["parts"].append({"part": part, "channel": chans[0], "old": list(old),
                                 "new": list(ref[part]), "ok": not todo})
        rows.append(row)
        if tgt_ch:
            targets[sn] = tgt_ch
            active[sn] = sec

    # 3) Channel yang dibersihkan per section: {sn: {channel: set(cc)}} (71/74 = penanda bass)
    strip = {}
    for sn, per_part in targets.items():
        m = {}
        for part, chans in per_part.items():
            for ch in chans:
                m[ch] = {0, 32, 71, 74} if part == "Bass" else {0, 32}
        strip[sn] = m

    def doomed(tick, raw):
        status = raw[0]
        for sn, sec in active.items():
            if not (sec["start"] <= tick < sec["end"]):
                continue
            if status == 0xF0:
                b = bytes(raw)
                if len(b) >= 10 and b[2:5] == b"\x43\x10\x4c" and b[7] in (0x72, 0x73):
                    ccs = strip[sn].get(b[6])
                    return bool(ccs) and 71 in ccs
                return False
            if status >= 0xF0:
                return False
            ccs = strip[sn].get(status & 0x0F)
            if not ccs:
                return False
            kind = status & 0xF0
            return (kind == 0xB0 and raw[1] in ccs) or kind == 0xC0
        return False

    # 4) Event yang perlu disisipkan di awal tiap section.
    inserts = {}
    for sn, sec in active.items():
        evs = []
        for part in VOICE_PARTS:
            for tch in targets[sn].get(part, []):
                msb, lsb, pc = ref[part]
                if msb is not None:
                    evs.append(bytes([0xB0 | tch, 0, msb]))
                if lsb is not None:
                    evs.append(bytes([0xB0 | tch, 32, lsb]))
                if pc is not None:
                    evs.append(bytes([0xC0 | tch, pc]))
                if part == "Bass":
                    for cc, val in sorted(BASS_CC_SET.items()):
                        evs.append(bytes([0xB0 | tch, cc, val]))
                    for addr_low, val in sorted(BASS_XG_SET.items()):
                        evs.append(_xg_part(tch, addr_low, val))
        if evs:
            inserts[sec["start"]] = evs

    events = [e for e in tgt.events if not doomed(*e)]
    for start in sorted(inserts, reverse=True):
        # Sisipkan TEPAT setelah marker/text section (event meta "FF ..") di tick
        # yang sama — jangan sebelum marker, biar tetap dianggap bagian section ini.
        lo, hi = 0, len(events)
        while lo < hi:
            mid = (lo + hi) // 2
            if events[mid][0] < start:
                lo = mid + 1
            else:
                hi = mid
        pos = lo
        j = lo
        while j < len(events) and events[j][0] == start:
            if events[j][1][0] == 0xFF:
                pos = j + 1
            j += 1
        events[pos:pos] = [(start, raw) for raw in inserts[start]]
    tgt.events = events

    out = bytearray()
    tgt.chunks[tgt.track_index][1] = sff.build_track(tgt.events)
    for name, payload in tgt.chunks:
        out += name + len(payload).to_bytes(4, "big") + payload

    report = {"sections": rows, "refs": {k: list(v) for k, v in ref.items()},
              "bass_cc": dict(BASS_CC_SET), "bass_xg": {("%02x" % k): v for k, v in BASS_XG_SET.items()}}
    return bytes(out), report


if __name__ == "__main__":
    # CLI sederhana: repair.py TARGET.STY TEMPLATE.STY OUT.STY [part_id,part_id,...] [fit|template]
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    tgt, tpl, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    ids = sys.argv[4].split(",") if len(sys.argv) > 4 and sys.argv[4] else None
    md = sys.argv[5] if len(sys.argv) > 5 else "fit"
    data, rep = repair(open(tgt, "rb").read(), open(tpl, "rb").read(), ids, md)
    open(out_path, "wb").write(data)
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    print("ditulis:", out_path)
