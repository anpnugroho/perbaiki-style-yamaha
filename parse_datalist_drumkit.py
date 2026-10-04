#!/usr/bin/env python3
"""Ambil kolom drum kit dari PDF Data List Yamaha (mis. PSR-S970/S770 hal.29).
Kolom dikenali dari posisi x fragmen teks: tiap kit punya rentang x sendiri.
Usage: parse_datalist_drumkit.py FILE.pdf KITIDX  (KITIDX: 0=HouseKit,1=DrumMachine,2=StudioKit,3=PowerKit1)
Output: JSON {note: nama} ke stdout.
"""
import sys, json
from pypdf import PdfReader

# rentang x kolom Full Name tiap kit (dari observasi layout halaman ini)
COLS = [(50, 185), (226, 300), (335, 412), (447, 520)]


def main():
    pdf, kit = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2
    lo, hi = COLS[kit]
    pg = PdfReader(pdf).pages[0]
    frags = []
    def v(text, cm, tm, fd, fs):
        t = text.strip()
        if t:
            frags.append((round(tm[5], 1), round(tm[4], 1), t))
    pg.extract_text(visitor_text=v)
    rows = {}
    for y, x, t in frags:
        rows.setdefault(y, []).append((x, t))
    ys = sorted(rows, reverse=True)
    out = {}
    note = 13
    for y in ys:
        cells = [t for x, t in sorted(rows[y]) if lo <= x < hi]
        if not cells:
            continue
        name = " ".join(cells).strip()
        if name.lower().startswith(('full name', 'note', 'kit name')):
            continue
        out[note] = name
        note += 1
        if note > 91:
            break
    json.dump(out, sys.stdout, indent=0, ensure_ascii=False)
    print("", file=sys.stderr)
    print(f"# {len(out)} note terbaca dari kolom kit #{kit}", file=sys.stderr)


if __name__ == '__main__':
    main()
