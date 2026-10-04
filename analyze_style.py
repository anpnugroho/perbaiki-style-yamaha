#!/usr/bin/env python3
"""Bedah 1 file .STY: section timeline, part per section, voice (bank+program) per channel.
Read-only, untuk analisa. Usage: analyze_style.py FILE.sty
"""
import struct, sys

def chunks(d):
    p = 0
    out = []
    while p + 8 <= len(d):
        name = d[p:p + 4]
        ln = struct.unpack('>I', d[p + 4:p + 8])[0]
        if p + 8 + ln > len(d):
            break
        out.append((name, p + 8, ln))
        p += 8 + ln
    return out


def main(f):
    d = open(f, 'rb').read()
    print(f"FILE: {f}\n  ukuran: {len(d):,} byte")
    if d[:4] != b'MThd':
        print("  bukan SFF terbaca (terproteksi?)", d[:12].hex(' '))
        return
    fmt, ntrk, div = struct.unpack('>HHH', d[8:14])
    bar_ticks = div * 4  # asumsi 4/4: 1 bar = 4 quarter
    print(f"  SMF format={fmt} tracks={ntrk} division={div} -> 1 bar 4/4 = {bar_ticks} tick")

    trk = None
    p = 14
    while p + 8 <= len(d) and d[p:p + 4] == b'MTrk':
        ln = struct.unpack('>I', d[p + 4:p + 8])[0]
        if trk is None:
            trk = d[p + 8:p + 8 + ln]
        p += 8 + ln
    print(f"  chunk: {[c[0].decode('latin1') for c in chunks(d)]}")

    i = 0; tick = 0; run = None
    marks = []; events = []
    bank = {}; prog = {}
    while i < len(trk):
        delta = 0
        while True:
            b = trk[i]; i += 1; delta = (delta << 7) | (b & 0x7F)
            if not (b & 0x80): break
        tick += delta
        if i >= len(trk): break
        st = trk[i]
        if st >= 0x80: i += 1; run = st
        else: st = run
        if st == 0xFF:
            mt = trk[i]; i += 1; ml = 0
            while True:
                b = trk[i]; i += 1; ml = (ml << 7) | (b & 0x7F)
                if not (b & 0x80): break
            data = trk[i:i + ml]; i += ml
            if mt in (1, 3, 6):
                marks.append((tick, mt, data.decode('latin1', 'replace')))
            if mt == 0x2F: break
        elif st in (0xF0, 0xF7):
            ml = 0
            while True:
                b = trk[i]; i += 1; ml = (ml << 7) | (b & 0x7F)
                if not (b & 0x80): break
            i += ml
        else:
            hi = st & 0xF0; ch = st & 0x0F
            if hi == 0x90:
                n, v = trk[i], trk[i + 1]; i += 2
                if v > 0: events.append((tick, ch, 'NOTE', n, v))
            elif hi == 0x80: i += 2
            elif hi == 0xB0:
                cc, val = trk[i], trk[i + 1]; i += 2
                if cc in (0, 32): bank.setdefault(ch, {})[cc] = val
                events.append((tick, ch, f'CC{cc}', val, 0))
            elif hi in (0xA0, 0xE0): i += 2
            elif hi == 0xC0:
                prog[ch] = trk[i]; i += 1
                events.append((tick, ch, 'PROG', trk[i - 1], 0))
            elif hi == 0xD0: i += 1

    sect = [(t, txt) for t, mt, txt in marks if mt == 6]
    print(f"\n=== SECTION (marker meta) — {len(sect)} buah ===")
    for idx, (t, nm) in enumerate(sect):
        nxt = sect[idx + 1][0] if idx + 1 < len(sect) else tick
        bars = (nxt - t) / bar_ticks
        print(f"  {nm:10s} tick {t:>8}  panjang {nxt - t:>8} tick = {bars:6.2f} bar")
    others = [(t, txt) for t, mt, txt in marks if mt in (1, 3)]
    print(f"\n=== track name / teks lain ({len(others)}) ===")
    for t, txt in others[:12]:
        print(f"  tick {t:>8}  '{txt[:60]}'")

    print("\n=== part aktif (channel) : voice bank/program ===")
    cnt = {}
    for tk, ch, kind, a, b in events:
        if kind == 'NOTE': cnt[ch] = cnt.get(ch, 0) + 1
    for ch in sorted(cnt):
        bk = bank.get(ch, {})
        print(f"  ch {ch:2d}: {cnt[ch]:5d} note | bank MSB={bk.get(0,'-')} LSB={bk.get(32,'-')} | prog={prog.get(ch,'-')}"
              f"{'  <-- DRUM' if ch == 9 else ''}")
    print("\n=== note pakai channel (0-indexed) ===")
    for tk, ch, kind, a, b in events:
        if kind == 'NOTE':
            print("   contoh pertama tiap ch: ", end=""); break
    seen = set()
    for tk, ch, kind, a, b in events:
        if kind == 'NOTE' and ch not in seen:
            seen.add(ch)
            print(f"   ch {ch:2d} tick {tk:>7} note {a:3d} vel {b}")


if __name__ == '__main__':
    main(sys.argv[1])
