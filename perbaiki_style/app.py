#!/usr/bin/env python3
"""app.py — UI lokal fitur "Perbaiki Style" (Yamaha PSR).

Jalan tanpa dependency (Python 3 stdlib saja):

    python3 app.py                 # http://127.0.0.1:3210
    python3 app.py --port 3210 --host 0.0.0.0

Alur: pilih file style (.STY) -> sistem membaca part-nya -> tekan "Perbaiki Style"
-> part target diganti sesuai style template -> unduh hasilnya.
"""
import argparse
import base64
import json
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repair  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
TEMPLATES = os.path.join(HERE, "templates")
OUT = os.path.join(HERE, "out")

DEFAULT_TEMPLATE_NAMES = ["Template V23.STY", "Template V23.sty", "template.STY", "template.sty", "TEMPLATE.STY"]
IGNORED_TEMPLATE_FILES = {"README.md", "sources.json", "sources.json.bak"}


def list_templates(include_donors=False):
    """File template utama di folder templates/.

    File yang dipakai sebagai donor per-part (tercatat di sources.json) tidak
    ditampilkan supaya daftar tetap bersih.
    """
    if not os.path.isdir(TEMPLATES):
        return []
    donors = set()
    if not include_donors:
        donors = {str(v) for v in (repair.load_sources() or {}).values()}
    out = []
    for name in sorted(os.listdir(TEMPLATES)):
        if name in IGNORED_TEMPLATE_FILES or name.startswith(".") or name in donors:
            continue
        if os.path.isfile(os.path.join(TEMPLATES, name)):
            out.append(name)
    return out


def template_by_name(name):
    """Ambil path template dari folder templates/ (hanya nama file, tanpa folder)."""
    base = os.path.basename(str(name or ""))
    if not base or base in IGNORED_TEMPLATE_FILES:
        return None
    path = os.path.join(TEMPLATES, base)
    return path if os.path.isfile(path) else None


def template_path():
    for name in DEFAULT_TEMPLATE_NAMES:
        p = os.path.join(TEMPLATES, name)
        if os.path.isfile(p):
            return p
    return None


def clean_name(name, fallback="style.STY"):
    """Ambil nama file apa adanya (spasi, @, &, -, dst dipertahankan).
    Hanya bagian folder yang dibuang + karakter kontrol dibersihkan."""
    base = str(name or "").replace("\\", "/").split("/")[-1]
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    base = base.lstrip(".")
    if not base:
        return fallback
    if "." not in base:
        base += ".STY"
    return base


# nama lama (dipakai di tempat lain kalau perlu)
safe_name = clean_name


class Handler(BaseHTTPRequestHandler):
    server_version = "perbaiki-style/0.1"

    # ---------- util ----------
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def log_message(self, fmt, *args):  # ringkas
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    # ---------- GET ----------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._file(os.path.join(STATIC, "index.html"))
        if path.startswith("/static/"):
            return self._file(os.path.join(STATIC, path[len("/static/"):]))
        if path == "/api/parts":
            return self._json(200, {"parts": repair.load_parts_map()})
        if path == "/api/template":
            tp = template_path()
            files = list_templates()
            info = {"available": bool(tp), "name": os.path.basename(tp) if tp else None,
                    "files": files, "sources": repair.load_sources()}
            if tp:
                try:
                    info["sections"] = [s["name"] for s in repair.sff.Style(tp).sections()]
                except Exception as exc:
                    info["error"] = str(exc)
            return self._json(200, info)
        return self._json(404, {"error": "tidak ditemukan"})

    def _file(self, path):
        if not os.path.isfile(path):
            return self._json(404, {"error": "file tidak ada"})
        ctype = "text/html; charset=utf-8"
        if path.endswith(".css"):
            ctype = "text/css; charset=utf-8"
        elif path.endswith(".js"):
            ctype = "application/javascript; charset=utf-8"
        with open(path, "rb") as fh:
            return self._send(200, fh.read(), ctype)

    # ---------- POST ----------
    def do_POST(self):
        path = self.path.split("?")[0]
        data = self._body()
        if path == "/api/analyze":
            return self._analyze(data)
        if path == "/api/repair":
            return self._repair(data)
        return self._json(404, {"error": "tidak ditemukan"})

    @staticmethod
    def _decode(data, key="data"):
        raw = data.get(key)
        if not raw:
            return None
        return base64.b64decode(raw)

    def _analyze(self, data):
        blob = self._decode(data)
        if not blob:
            return self._json(400, {"error": "file style belum dikirim"})
        try:
            info = repair.analyze(blob)
        except Exception as exc:
            return self._json(400, {"error": f"gagal baca style: {exc}"})
        info["filename"] = safe_name(data.get("name"))
        return self._json(200, info)

    def _repair(self, data):
        blob = self._decode(data)
        if not blob:
            return self._json(400, {"error": "file style belum dikirim"})

        tpl_blob = self._decode(data, "template")
        tpl_note = None
        if tpl_blob:
            tpl_note = "dari unggahan"
        else:
            chosen = template_by_name(data.get("template_name"))
            tp = chosen or template_path()
            if not tp:
                return self._json(400, {"error": "template belum ada. Pilih template di daftar, unggah file template, "
                                                 "atau simpan sebagai templates/template.STY"})
            tpl_blob = open(tp, "rb").read()
            tpl_note = os.path.basename(tp)

        part_ids = data.get("parts") or None
        mode = data.get("mode") or "fit"

        # Template campuran: part tertentu bisa punya donor sendiri (templates/sources.json).
        overrides = {}
        for p in repair.load_parts_map():
            if part_ids and p["id"] not in part_ids:
                continue
            path = repair.source_file(p["id"])
            if path:
                with open(path, "rb") as fh:
                    overrides[p["id"]] = fh.read()

        # Donor khusus part Bass (kit/filter/EQ diambil dari file lain).
        bass_overrides = {}
        for pid, fname in repair.load_bass_sources().items():
            if part_ids and pid not in part_ids:
                continue
            path = os.path.join(repair.TEMPLATES_DIR, fname)
            if os.path.isfile(path):
                with open(path, "rb") as fh:
                    bass_overrides[pid] = fh.read()

        try:
            result, report = repair.repair(blob, tpl_blob, part_ids, mode, overrides, bass_overrides)
        except Exception as exc:
            return self._json(400, {"error": f"gagal memperbaiki style: {exc}"})

        # Fitur baru (opsional): rapikan Bass/Rhythm1/Rhythm2 di Intro 1-3 & Ending 1
        # mengikuti Main A / Fill In A. Fitur lama di atas tidak diubah.
        if data.get("fix_intro_ending"):
            try:
                result, fx_report = repair.fix_intro_ending(result)
                report["intro_ending"] = fx_report
            except Exception as exc:
                return self._json(400, {"error": f"gagal merapikan Intro/Ending: {exc}"})

        os.makedirs(OUT, exist_ok=True)
        os.makedirs(os.path.join(OUT, "arsip"), exist_ok=True)
        out_name = clean_name(data.get("name"))
        result_path = os.path.join(OUT, out_name)
        with open(result_path, "wb") as fh:
            fh.write(result)
        # arsip ber-timestamp (backup otomatis, tanpa memperlambat proses)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        with open(os.path.join(OUT, "arsip", f"{stamp}__{out_name}"), "wb") as fh:
            fh.write(result)

        report["template_source"] = tpl_note
        report["sources"] = repair.load_sources()
        report["templates_available"] = list_templates()
        report["output_file"] = out_name
        report["output_bytes"] = len(result)
        return self._json(200, {"report": report, "filename": out_name,
                                "data": base64.b64encode(result).decode("ascii")})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=3210)
    args = ap.parse_args()

    os.makedirs(TEMPLATES, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    tp = template_path()
    print(f"Perbaiki Style jalan di http://{args.host}:{args.port}")
    print(f"Template default: {tp if tp else 'BELUM ADA (unggah lewat UI / taruh di templates/template.STY)'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\ndihentikan")


if __name__ == "__main__":
    main()
