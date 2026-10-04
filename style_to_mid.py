#!/usr/bin/env python3
"""style_to_mid.py — export style Yamaha (.STY) jadi MIDI standar (SMF type 1).
Gunanya: dengar / edit di DAW, atau lihat isi section tertentu sebelum diganti.

Contoh:
  python3 style_to_mid.py samples/BASE_LUKA_DISINI_E_V25.STY out/base_full.mid
  python3 style_to_mid.py ......STY out/endingA.mid --section "Ending A"
"""
import sys, struct
import sff

PART_NAMES = {9: "Rhythm1", 10: "Rhythm2", 11: "Bass", 12: "Chord1", 13: "Chord2",
              14: "Pad", 15: "Phrase1", 16: "Phrase2"}


def build_header(fmt, ntrk, div):
    return b"MThd" + struct.pack(">IHHH", 6, fmt, ntrk, div)


def track_chunk(events):
    return b"MTrk" + struct.pack(">I", len(sff.build_track(events))) + sff.build_track(events)


def main():
    sty_path, out_path = sys.argv[1], sys.argv[2]
    section_name = None
    if "--section" in sys.argv:
        section_name = sys.argv[sys.argv.index("--section") + 1]

    st = sff.Style(sty_path)
    div = st.division
    bar = st.bar_ticks

    if section_name:
        sec = st.section(section_name)
        base = sec["start"]
        evs = [(t - base, r) for t, r in st.events if sec["start"] <= t < sec["end"]]
        markers = [(0, "start:" + sec["name"]), (sec["end"] - base, "end")]
    else:
        base = 0
        evs = list(st.events)
        markers = [(s["start"], s["name"]) for s in st.sections()]

    # voice terakhir sebelum section (biar MIDI hasil export tetap punya voice yang benar)
    if section_name:
        last_voice = {}
        for t, raw in st.events:
            if t >= sec["start"]:
                break
            if raw[0] & 0xF0 in (sff.CC, sff.PC):
                last_voice.setdefault(sff.ev_channel(raw), []).append(raw)
        prepend = [(0, r) for ch in sorted(last_voice) for r in last_voice[ch]]
        evs = prepend + evs

    # track 0: tempo + marker
    t0 = []
    if st.tempo:
        us = int(60000000 / st.tempo)
        t0.append((0, bytes([0xFF, 0x51, 3]) + us.to_bytes(3, "big")))
    for tick, name in markers:
        data = name.encode("latin1")
        t0.append((tick, bytes([0xFF, 6]) + sff.varlen(len(data)) + data))
    t0.sort(key=lambda e: e[0])
    t0.append((max([t for t, _ in evs] + [0]) + div * 4, bytes([0xFF, 0x2F, 0])))

    tracks = []
    by_ch = {}
    for t, raw in evs:
        if raw[0] == sff.META or raw[0] in (sff.SYSEX, sff.SYSEX_ESC):
            continue
        by_ch.setdefault(sff.ev_channel(raw) + 1, []).append((t, raw))
    tracks.append((b"Tempo/Marker", t0))
    for ch in sorted(by_ch):
        nm = PART_NAMES.get(ch, f"ch{ch}")
        lst = sorted(by_ch[ch], key=lambda e: e[0])
        lst.append((max(t for t, _ in lst) + div, bytes([0xFF, 0x2F, 0])))
        tracks.append((f"{ch}-{nm}".encode(), lst))

    out = bytearray(build_header(1, len(tracks), div))
    for name, ev in tracks:
        # sisipkan track-name biar kebaca di DAW
        ev = [(0, bytes([0xFF, 3]) + sff.varlen(len(name)) + name)] + ev
        out += track_chunk(ev)
    open(out_path, "wb").write(bytes(out))
    print(f"export: {out_path}")
    print(f"  division={div} tempo={st.tempo} {'section=' + section_name if section_name else 'seluruh style'}")
    print(f"  track: {len(tracks)} (1 tempo/marker + {len(tracks) - 1} part)")
    for name, ev in tracks:
        n = sum(1 for _, r in ev if r[0] & 0xF0 == sff.NOTE_ON and r[2] > 0)
        print(f"    {name.decode() if isinstance(name, bytes) else name:16s} {len(ev):6d} event, {n:5d} note")


if __name__ == "__main__":
    main()
