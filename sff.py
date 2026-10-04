#!/usr/bin/env python3
"""sff.py — library baca/tulis file style Yamaha (.STY, SFF1/SFF2).

Yang ditangani:
  - chunk MThd / MTrk / CASM / OTSc
  - track events disimpan sebagai (tick_absolut, raw_bytes) supaya bisa ditulis ulang tanpa kehilangan apa pun
  - chunk selain MTrk (CASM, OTSc, ...) disimpan utuh byte-per-byte

Dipakai oleh: style_to_mid.py, style_inject.py, style_report.py
"""
import struct

NOTE_ON, NOTE_OFF, POLY_AT, CC, PC, CH_AT, PB = 0x90, 0x80, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0
META, SYSEX, SYSEX_ESC, EOT = 0xFF, 0xF0, 0xF7, 0x2F


def varlen(n):
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def read_varlen(buf, i):
    v = 0
    while True:
        b = buf[i]
        i += 1
        v = (v << 7) | (b & 0x7F)
        if not (b & 0x80):
            return v, i


def parse_track(track):
    """-> list[(tick_abs, raw_bytes)]; raw_bytes SELALU memuat status byte (running status di-resolve)."""
    ev, i, tick, run = [], 0, 0, None
    while i < len(track):
        delta, i = read_varlen(track, i)
        tick += delta
        if i >= len(track):
            break
        st = track[i]
        if st >= 0x80:
            i += 1
            run = st
        else:
            st = run
            if st is None:
                raise ValueError("running status tanpa status sebelumnya")
        if st == META:
            mt = track[i]
            i += 1
            ln, i = read_varlen(track, i)
            data = track[i:i + ln]
            i += ln
            ev.append((tick, bytes([META, mt]) + varlen(ln) + data))
            if mt == EOT:
                break
        elif st in (SYSEX, SYSEX_ESC):
            ln, i = read_varlen(track, i)
            data = track[i:i + ln]
            i += ln
            ev.append((tick, bytes([st]) + varlen(ln) + data))
        else:
            n = 2 if (st & 0xF0) in (NOTE_OFF, NOTE_ON, POLY_AT, CC, PB) else 1
            data = track[i:i + n]
            i += n
            ev.append((tick, bytes([st]) + data))
    return ev


def build_track(events):
    out, prev = bytearray(), 0
    for tick, raw in events:
        if tick < prev:
            raise ValueError(f"urutan tick mundur: {tick} < {prev}")
        out += varlen(tick - prev)
        out += raw
        prev = tick
    return bytes(out)


# ---------- helper baca event ----------
def ev_status(raw):
    return raw[0]


def ev_kind(raw):
    st = raw[0]
    if st == META:
        return "meta", raw[1]
    if st in (SYSEX, SYSEX_ESC):
        return "sysex", None
    hi = st & 0xF0
    return {NOTE_ON: "note_on", NOTE_OFF: "note_off", POLY_AT: "poly_at", CC: "cc",
            PC: "prog", CH_AT: "ch_at", PB: "pitch_bend"}.get(hi, "?"), None


def ev_channel(raw):
    return raw[0] & 0x0F


def meta_text(raw):
    if raw[0] != META or raw[1] not in (1, 2, 3, 4, 5, 6, 7):
        return None
    ln, i = read_varlen(raw, 2)
    return raw[i:i + ln].decode("latin1", "replace")


def tempo_bpm(raw):
    if raw[0] == META and raw[1] == 0x51 and len(raw) >= 6:
        us = int.from_bytes(raw[3:6], "big")
        return round(60000000 / us, 3) if us else None
    return None


class Style:
    def __init__(self, path=None, data=None, strict=True):
        if data is None:
            data = open(path, "rb").read()
        self.chunks = []
        p = 0
        while p + 8 <= len(data):
            name = data[p:p + 4]
            ln = struct.unpack(">I", data[p + 4:p + 8])[0]
            if p + 8 + ln > len(data):
                if strict:
                    raise ValueError(f"chunk {name!r} panjang {ln} melewati akhir file")
                break
            self.chunks.append([name, data[p + 8:p + 8 + ln]])
            p += 8 + ln
        self.track_index = None
        for i, (n, _) in enumerate(self.chunks):
            if n == b"MTrk":
                self.track_index = i
                self.events = parse_track(self.chunks[i][1])
                break
        if self.track_index is None:
            raise ValueError("tidak ada chunk MTrk (bukan SFF/SMF yang didukung)")

    # --- info dasar ---
    @property
    def header(self):
        """(format, ntracks, division)"""
        pl = self.chunks[0][1]
        fmt, ntrk, div = struct.unpack(">HHH", pl[0:6])
        return fmt, ntrk, div

    @property
    def division(self):
        return self.header[2]

    @property
    def bar_ticks(self):
        """asumsi 4/4"""
        return self.division * 4

    @property
    def tempo(self):
        for _, raw in self.events:
            b = tempo_bpm(raw)
            if b:
                return b
        return None

    def markers(self, meta_type=6):
        out = []
        for tick, raw in self.events:
            if raw[0] == META and raw[1] == meta_type:
                out.append((tick, meta_text(raw)))
        return out

    def sections(self):
        """-> list of dict(name, start, end) berdasarkan marker meta 0x06"""
        ms = [(t, txt) for t, txt in self.markers(6) if txt]
        out = []
        end_tick = max(t for t, _ in self.events)
        for i, (t, nm) in enumerate(ms):
            if nm == "SFF2":          # penanda format, bukan section
                continue
            nxt = ms[i + 1][0] if i + 1 < len(ms) else end_tick
            out.append({"name": nm, "start": t, "end": nxt, "bars": round((nxt - t) / self.bar_ticks, 3)})
        return out

    def section(self, name):
        for s in self.sections():
            if s["name"].lower() == name.lower():
                return s
        raise KeyError(f"section {name!r} tidak ada. Tersedia: {[s['name'] for s in self.sections()]}")

    def events_of(self, section):
        return [(t, r) for t, r in self.events if section["start"] <= t < section["end"]]

    # --- tulis ---
    def save(self, path):
        self.chunks[self.track_index][1] = build_track(self.events)
        out = bytearray()
        for n, pl in self.chunks:
            out += n + struct.pack(">I", len(pl)) + pl
        open(path, "wb").write(bytes(out))
        return path


def midi_note_name(n):
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return f"{names[n % 12]}{n // 12 - 1}"
