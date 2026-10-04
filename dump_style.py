#!/usr/bin/env python3
"""Parser awal Yamaha style (.STY / SFF2).
Dump: chunk SMF, marker section di track, dan struktur CASM (section -> part -> parameter).
Usage: dump_style.py FILE.sty [--json OUT.json]
"""
import struct, sys, json, re


def rd(buf, off):
    name = buf[off:off + 4]
    ln = struct.unpack('>I', buf[off + 4:off + 8])[0]
    return name, off + 8, ln, off + 8 + ln


def smf_markers(d):
    """Ambil meta event teks/marker dari track SMF."""
    out = []
    if d[:4] != b'MThd':
        return None
    _, off, ln, end = rd(d, 0)
    p = end
    track = 0
    while p + 8 <= len(d) and d[p:p + 4] == b'MTrk':
        _, s, tlen, tend = rd(d, p)
        i = s
        abs_tick = 0
        while i < tend:
            delta = 0
            while True:
                b = d[i]; i += 1; delta = (delta << 7) | (b & 0x7F)
                if not (b & 0x80): break
            abs_tick += delta
            if i >= tend: break
            status = d[i]
            if status >= 0x80:
                i += 1
            if status == 0xFF:
                mtype = d[i]; i += 1
                mlen = 0
                while True:
                    b = d[i]; i += 1; mlen = (mlen << 7) | (b & 0x7F)
                    if not (b & 0x80): break
                data = d[i:i + mlen]; i += mlen
                if mtype in (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07):
                    txt = data.decode('latin1', 'replace')
                    out.append({"track": track, "tick": abs_tick, "meta": hex(mtype), "text": txt})
            elif status in (0xF0, 0xF7):
                mlen = 0
                while True:
                    b = d[i]; i += 1; mlen = (mlen << 7) | (b & 0x7F)
                    if not (b & 0x80): break
                i += mlen
            else:
                hi = status & 0xF0
                if hi in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                    i += 2
                elif hi in (0xC0, 0xD0):
                    i += 1
            if status == 0xFF and mtype == 0x2F:
                break
        p = tend
        track += 1
    return out


def parse_casm(d):
    off = d.find(b'CASM')
    if off < 0:
        return None
    name, s, ln, send = rd(d, off)
    sections = []
    p = s
    while p + 8 <= send and d[p:p + 4] == b'CSEG':
        _, cs, clen, cend = rd(d, p)
        sec = {"name": "", "parts": []}
        q = cs
        while q + 8 <= cend:
            cname = d[q:q + 4]
            if cname == b'Sdec':
                _, ds, dlen, dend = rd(d, q)
                sec["name"] = d[ds:ds + dlen].decode('latin1', 'replace')
                sec["sdec_raw"] = d[ds:ds + dlen].hex(' ')
                q = dend
            elif cname == b'Ctb2':
                _, bs, blen, bend = rd(d, q)
                payload = d[bs:bs + blen]
                nl = payload[0]
                partname = payload[1:1 + nl].decode('latin1', 'replace')
                params = payload[1 + nl:]
                sec["parts"].append({"part": partname.strip(), "params_hex": params.hex(' '),
                                     "len": len(params)})
                q = bend
            else:
                _, _, blen, bend = rd(d, q)
                q = bend
        sections.append(sec)
        p = cend
    return {"casm_len": ln, "sections": sections}


def main():
    f = sys.argv[1]
    d = open(f, 'rb').read()
    print(f"FILE: {f} ({len(d):,} byte)")
    if d[:4] != b'MThd':
        print("  ⚠️ Bukan SMF/SFF yang bisa dibaca (kemungkinan SET terproteksi/terenkripsi).")
        print("  header:", d[:16].hex(' '))
        return 1
    _, _, _, _ = rd(d, 0)
    fmt, ntrk, div = struct.unpack('>HHH', d[8:14])
    print(f"  SMF format={fmt} tracks={ntrk} division={div} ({div/4 if div else 0:.0f} ppq)")
    marks = smf_markers(d)
    print(f"\n  --- marker/track-name di track ({len(marks)} entri) ---")
    for m in marks:
        print(f"    tick {m['tick']:>7}  meta {m['meta']}  '{m['text']}'")
    cas = parse_casm(d)
    if not cas:
        print("\n  (tanpa CASM chunk)")
        return 0
    print(f"\n  --- CASM: {len(cas['sections'])} section (panjang chunk {cas['casm_len']}) ---")
    for s in cas['sections']:
        print(f"    [{s['name']}] {len(s['parts'])} part")
        for pt in s['parts']:
            print(f"        {pt['part']:9s} len={pt['len']:2d}  {pt['params_hex']}")
    if '--json' in sys.argv:
        out = sys.argv[sys.argv.index('--json') + 1]
        json.dump({"file": f, "markers": marks, "casm": cas}, open(out, 'w'), indent=1)
        print(f"\n  -> {out}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
