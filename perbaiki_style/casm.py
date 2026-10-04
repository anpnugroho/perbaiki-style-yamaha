#!/usr/bin/env python3
"""casm.py — baca blok CASM style Yamaha (SFF1/SFF2).

Tiap section di CASM menyimpan daftar part + **channel MIDI** yang dipakai part itu.
Ini kunci untuk memindahkan isi part dari satu style ke style lain: nomor channel
bisa BEDA antar style, jadi harus di-remap berdasarkan NAMA part (Rhythm1, Rhythm2,
Bass, Chord1, Chord2, Pad, Phrase1, Phrase2, Syn.SFX, ...).
"""
import re

PART_NAMES = [
    b"Rhythm1 ", b"Rhythm2 ", b"Bass    ", b"Chord1  ", b"Chord2  ",
    b"Pad     ", b"Phrase1 ", b"Phrase2 ", b"Syn.SFX ", b"Rhy1    ", b"Rhy2    ",
]

HEADER_BASE = 12  # Sdec(4) + panjang-nama(4) + "Ctb2"(4)


def _sections_raw(casm_bytes):
    """Iterator (nama_section, payload) untuk tiap CSEG di dalam CASM."""
    i = 0
    while i + 8 <= len(casm_bytes):
        if casm_bytes[i:i + 4] != b"CSEG":
            break
        length = int.from_bytes(casm_bytes[i + 4:i + 8], "big")
        payload = casm_bytes[i + 8:i + 8 + length]
        namelen = int.from_bytes(payload[4:8], "big")
        name = payload[8:8 + namelen].decode("latin1").strip()
        yield name, payload
        i += 8 + length


def header_len(payload):
    """Panjang header dalam satu CSEG (tergantung panjang nama section)."""
    return HEADER_BASE + int.from_bytes(payload[4:8], "big")


def parse(casm_bytes):
    """-> {nama_section: [ (nama_part, channel_0based), ... ]}"""
    out = {}
    for name, payload in _sections_raw(casm_bytes):
        body = payload[header_len(payload):]
        found = []
        for pname in PART_NAMES:
            start = 0
            while True:
                j = body.find(pname, start)
                if j < 1:
                    break
                found.append((j, pname.decode("latin1").strip(), body[j - 1]))
                start = j + 1
        found.sort(key=lambda x: x[0])
        out[name] = [(n, ch) for _, n, ch in found]
    return out


def part_channels(section_parts):
    """[(part, ch)] -> {part: ch}"""
    return {n: ch for n, ch in section_parts}


def build_remap(donor_parts, target_parts):
    """
    Peta channel: donor -> target, supaya part yang sama tetap nyala di style target.

    donor_parts / target_parts : [ (nama_part, channel_0based), ... ]
    """
    tgt_by_name = {}
    for n, ch in target_parts:
        tgt_by_name.setdefault(n, ch)
    tgt_channels = {ch for _, ch in target_parts}

    remap = {}
    for n, ch in donor_parts:
        if n in tgt_by_name:
            remap[ch] = tgt_by_name[n]
        elif ch in tgt_channels:
            remap[ch] = ch  # tidak ada padanan nama, tapi channel-nya valid di target
    return remap


CHANNEL_STATUS = (0x80, 0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0)


def remap_event(raw, remap):
    """Ganti nomor channel pada event MIDI (kalau ada di peta)."""
    if not remap or not raw:
        return raw
    status = raw[0]
    if status < 0xF0 and (status & 0xF0) in CHANNEL_STATUS:
        ch = status & 0x0F
        if ch in remap and remap[ch] != ch:
            return bytes([(status & 0xF0) | remap[ch]]) + bytes(raw[1:])
    return raw


def load(style):
    """Ambil CASM dari objek sff.Style."""
    for name, payload in style.chunks:
        if name == b"CASM":
            return parse(payload)
    return {}


def sections_raw(casm_bytes):
    return list(_sections_raw(casm_bytes))


def replace_sections(target_casm, donor_casm, names):
    """
    Ganti CSEG (konfigurasi part+channel) beberapa section di CASM target
    dengan milik donor — supaya part yang ditempel benar-benar dikenali keyboard
    persis seperti di style template (channel, voice, aturan chord).
    """
    tgt = sections_raw(target_casm)
    don = {n: p for n, p in sections_raw(donor_casm)}
    consumed = sum(8 + len(p) for _, p in tgt)
    trail = target_casm[consumed:]

    out = bytearray()
    replaced = []
    for name, payload in tgt:
        use = don.get(name, payload) if name in names else payload
        if name in names and name in don:
            replaced.append(name)
        out += b"CSEG" + len(use).to_bytes(4, "big") + use
    out += trail
    return bytes(out), replaced
