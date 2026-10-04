#!/usr/bin/env python3
"""style_inject.py — suntik konten MIDI (rekaman) ke slot section style Yamaha.

Cara kerja (aman, tanpa menebak CASM):
  - section target dibersihkan HANYA dari event nada (note on/off, pitch bend, channel pressure)
  - voice (CC0/CC32/PC), marker, SysEx, CASM, OTSc → SEMUA dibiarkan seperti base
  - event dari MIDI Mas disisipkan pada posisi tick yang sama relatif ke awal section

Contoh:
  # lihat dulu tanpa menulis file
  python3 style_inject.py samples/BASE_LUKA_DISINI_E_V25.STY out/new.sty \
      --put "Ending A=out/endingA.mid:1-16" --put "Intro C=out/introC.mid:1-28" --dry-run

  # pakai mapping channel kalau rekaman pakai channel lain (ch MIDI masuk : ch style)
  python3 style_inject.py BASE.STY OUT.STY --put "Ending A=rec.mid:1-16" --map "1:8,2:10,3:11"

  # kalau rekaman pop temponya separuh dangdut → dipercepat 2x
  python3 style_inject.py BASE.STY OUT.STY --put "Ending A=rec.mid:1-32" --time-scale 0.5
"""
import sys, struct
import sff

SLOT_ALIAS = {
    "ending1": "Ending A", "ending2": "Ending B", "ending3": "Ending C",
    "intro1": "Intro A", "intro2": "Intro B", "intro3": "Intro C",
    "maina": "Main A", "mainb": "Main B", "mainc": "Main C", "maind": "Main D",
}


def read_smf(path):
    """-> (division, list[(tick, raw)]) gabungan semua track, meta dibuang."""
    d = open(path, "rb").read()
    if d[:4] != b"MThd":
        raise ValueError(f"{path} bukan MIDI standar")
    fmt, ntrk, div = struct.unpack(">HHH", d[8:14])
    p = 14
    events = []
    for _ in range(ntrk):
        if d[p:p + 4] != b"MTrk":
            break
        ln = struct.unpack(">I", d[p + 4:p + 8])[0]
        trk = d[p + 8:p + 8 + ln]
        p += 8 + ln
        for tick, raw in sff.parse_track(trk):
            if raw[0] == sff.META or raw[0] in (sff.SYSEX, sff.SYSEX_ESC):
                continue
            events.append((tick, raw))
    events.sort(key=lambda e: e[0])
    return div, events


def parse_map(spec):
    m = {}
    if not spec:
        return m
    for part in spec.split(","):
        a, b = part.split(":")
        m[int(a)] = int(b)
    return m


def put_section(st, section, midi_path, bar_from, bar_to, chmap, time_scale, import_cc):
    sec = st.section(section)
    in_div, in_ev = read_smf(midi_path)
    in_bar = in_div * 4
    start_t = (bar_from - 1) * in_bar
    end_t = bar_to * in_bar
    ratio = st.division / in_div

    keep, removed = [], 0
    for t, raw in st.events:
        if not (sec["start"] <= t < sec["end"]):
            keep.append((t, raw))
            continue
        k, _ = sff.ev_kind(raw)
        drop = k in ("note_on", "note_off", "pitch_bend", "ch_at")
        if import_cc and k == "cc":
            drop = True
        if drop:
            removed += 1
        else:
            keep.append((t, raw))

    added, overflow = [], 0
    for t, raw in in_ev:
        if not (start_t <= t < end_t):
            continue
        nt = sec["start"] + int(round((t - start_t) * ratio * time_scale))
        k, _ = sff.ev_kind(raw)
        if k == "cc" and not import_cc:
            continue
        if k not in ("note_on", "note_off", "pitch_bend", "ch_at", "cc"):
            continue
        ch = sff.ev_channel(raw) + 1
        out_ch = chmap.get(ch, ch)
        if not 1 <= out_ch <= 16:
            continue
        raw2 = bytes([(raw[0] & 0xF0) | (out_ch - 1)]) + raw[1:]
        if nt >= sec["end"]:
            overflow += 1
            continue
        added.append((nt, raw2))

    st.events = sorted(keep + added, key=lambda e: (e[0], 0 if e[1][0] == sff.META else 1))
    print(f"[{section}] {sec['bars']:.0f} bar (tick {sec['start']}–{sec['end']})")
    print(f"   dibuang  : {removed} event nada lama")
    print(f"   disisip  : {len(added)} event dari {midi_path} (bar {bar_from}–{bar_to})")
    if overflow:
        print(f"   ⚠️ {overflow} event melewati akhir section → dibuang (rekaman lebih panjang dari slot)")
    return added


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    base, out = a[0], a[1]
    puts, mapping, time_scale, import_cc, dry = [], None, 1.0, False, "--dry-run" in a
    i = 2
    while i < len(a):
        if a[i] == "--put":
            puts.append(a[i + 1]); i += 2
        elif a[i] == "--map":
            mapping = a[i + 1]; i += 2
        elif a[i] == "--time-scale":
            time_scale = float(a[i + 1]); i += 2
        elif a[i] == "--import-cc":
            import_cc = True; i += 1
        else:
            i += 1
    chmap = parse_map(mapping)

    st = sff.Style(base)
    print(f"base: {base}")
    print(f"  division={st.division} tempo={st.tempo} section={len(st.sections())}\n")
    for spec in puts:
        slot, rest = spec.split("=", 1)
        mid, rng = rest.rsplit(":", 1)
        b1, b2 = rng.split("-")
        name = SLOT_ALIAS.get(slot.lower().replace(" ", ""), slot)
        put_section(st, name, mid, int(b1), int(b2), chmap, time_scale, import_cc)

    # urutkan ulang & pastikan end-of-track di akhir
    st.events = [e for e in st.events if not (e[1][0] == sff.META and e[1][1] == sff.EOT)]
    st.events.sort(key=lambda e: (e[0], 0 if e[1][0] == sff.META else 1))
    st.events.append((max(t for t, _ in st.events), bytes([0xFF, 0x2F, 0])))

    if dry:
        print("\n(--dry-run: file TIDAK ditulis)")
        return 0
    st.save(out)
    print(f"\ntersimpan: {out}")

    # verifikasi: baca ulang
    chk = sff.Style(out)
    print("verifikasi hasil:")
    for s in chk.sections():
        if any(SLOT_ALIAS.get(p.split('=')[0].lower().replace(' ', ''), p.split('=')[0]) == s["name"] for p in puts):
            ch = {}
            for t, raw in chk.events:
                if s["start"] <= t < s["end"] and raw[0] & 0xF0 == sff.NOTE_ON and raw[2] > 0:
                    c = (raw[0] & 0x0F) + 1
                    ch[c] = ch.get(c, 0) + 1
            print(f"   {s['name']:10s} {s['bars']:5.1f} bar | note per channel(1-16): {dict(sorted(ch.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
