#!/usr/bin/env python3
"""style_report.py — laporan struktur 1 style: section, panjang bar, part/channel aktif, voice per section.
Usage: python3 style_report.py FILE.STY [OUT.md]
"""
import sys
import sff

PART = {9: "Rhythm1", 10: "Rhythm2", 11: "Bass", 12: "Chord1", 13: "Chord2",
        14: "Pad", 15: "Phrase1", 16: "Phrase2"}


def main():
    path = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None
    st = sff.Style(path)
    L = []
    L.append(f"# Cetakan style: {path.split('/')[-1]}")
    L.append("")
    L.append(f"- Division: {st.division} (1 bar 4/4 = {st.bar_ticks} tick) · Tempo: {st.tempo} BPM")
    L.append(f"- Chunk: {', '.join(c[0].decode('latin1') for c in st.chunks)}")
    L.append(f"- Jumlah section: {len(st.sections())}")
    L.append("")
    L.append("| Section | Bar | Part aktif (channel MIDI → jumlah note) | Voice per channel |")
    L.append("|---|---|---|")

    cur = {}
    voices = {}   # section name -> {ch: voice}
    for t, raw in st.events:
        k, _ = sff.ev_kind(raw)
        ch = raw[0] & 0x0F
        if raw[0] & 0xF0 == sff.CC and raw[1] in (0, 32):
            cur.setdefault(ch, {})[raw[1]] = raw[2]
        elif raw[0] & 0xF0 == sff.PC:
            cur.setdefault(ch, {})["pc"] = raw[1]
            for s in st.sections():
                if s["start"] <= t < s["end"]:
                    voices.setdefault(s["name"], {})[ch] = dict(cur[ch])
                    break

    for s in st.sections():
        cnt = {}
        for t, raw in st.events:
            if s["start"] <= t < s["end"] and raw[0] & 0xF0 == sff.NOTE_ON and raw[2] > 0:
                c = (raw[0] & 0x0F) + 1
                cnt[c] = cnt.get(c, 0) + 1
        parts = ", ".join(f"ch{c}({PART.get(c, '?')}):{n}" for c, n in sorted(cnt.items()) if n)
        vs = voices.get(s["name"], {})
        vtxt = ", ".join(f"ch{c+1}:{v.get(0,'-')}-{v.get(32,'-')}-{v.get('pc','-')}"
                         for c, v in sorted(vs.items()) if len(v) >= 2)
        L.append(f"| {s['name']} | {s['bars']:.0f} | {parts} | {vtxt} |")

    txt = "\n".join(L) + "\n"
    if out:
        open(out, "w").write(txt)
        print(f"ditulis: {out}")
    else:
        print(txt)


if __name__ == "__main__":
    main()
