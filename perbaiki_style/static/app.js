(function () {
  const $ = (id) => document.getElementById(id);
  let styleB64 = null, styleName = '', fileMeta = null, sources = {}, tplMain = null, lastInfo = null;

  const b64 = (file) => new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(String(fr.result).split(',')[1] || '');
    fr.onerror = rej;
    fr.readAsDataURL(file);
  });

  async function post(url, payload) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || 'Gagal memproses');
    return data;
  }

  // --- template default ---
  fetch('/api/template').then((r) => r.json()).then((t) => {
    sources = t.sources || {};
    tplMain = t.name || null;
    const files = t.files || [];

    if (files.length > 1) {
      $('tpl-select-wrap').hidden = false;
      $('tpl-current').textContent = '';
      $('tpl-select').innerHTML = files
        .map((f) => `<option value="${f}"${f === tplMain ? ' selected' : ''}>${f}</option>`).join('');
    } else {
      $('tpl-select-wrap').hidden = true;
      $('tpl-select').innerHTML = files.length ? `<option value="${files[0]}" selected>${files[0]}</option>` : '<option value=""></option>';
      $('tpl-current').innerHTML = t.available
        ? `Template aktif: <b>${t.name || files[0]}</b>`
        : '<b>Belum ada template</b> — unggah file template di bawah';
    }

    $('tpl-badge').textContent = t.available ? 'template: ' + (t.name || files[0] || '—') : 'template: belum ada';
    $('tpl-badge').classList.toggle('ok', !!t.available);
    if (lastInfo) renderParts(lastInfo);
  }).catch(() => {});

  function sumberPart(id) {
    if (sources[id]) return sources[id];
    const pilih = $('tpl-select') ? $('tpl-select').value : '';
    return pilih || tplMain || '— unggahan manual —';
  }

  // --- pilih file style ---
  $('style-file').addEventListener('change', async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    styleName = f.name;
    $('style-name').innerHTML = '📄 <b>' + f.name + '</b>';
    $('msg').textContent = '';
    styleB64 = await b64(f);
    await analyze();
  });

  $('tpl-file').addEventListener('change', (e) => {
    const f = e.target.files[0];
    if (!f) return;
    fileMeta = f;
    $('tpl-name').innerHTML = '📄 <b>' + f.name + '</b> (dipakai untuk proses ini)';
  });

  async function analyze() {
    try {
      const info = await post('/api/analyze', { name: styleName, data: styleB64 });
      lastInfo = info;
      $('parts-panel').hidden = false;
      const st = info.style;
      renderParts(info);
      $('msg').textContent = `Division ${st.division} · ${st.bar_ticks} tick/bar · tempo ${st.tempo ?? '?'} BPM`;
    } catch (err) {
      $('msg').textContent = err.message;
    }
  }

  function renderParts(info) {
    $('parts').innerHTML = info.parts.map((p) => `
        <tr>
          <td><label class="pick"><input type="checkbox" class="p" value="${p.id}" checked /> ${p.label}</label></td>
          <td class="muted">${p.section_name || p.section || '—'}</td>
          <td class="muted small">${sumberPart(p.id)}</td>
          <td class="num">${p.bars ?? '—'}</td>
          <td class="num">${p.found ? p.notes : '—'}</td>
          <td>${p.found ? '<span class="ok-tag">ada</span>' : '<span class="no-tag">tidak ada</span>'}</td>
        </tr>`).join('');
  }

  $('tpl-select').addEventListener('change', () => { if (lastInfo) renderParts(lastInfo); });

  $('check-all').addEventListener('change', (e) => {
    document.querySelectorAll('input.p').forEach((c) => { c.checked = e.target.checked; });
  });

  $('go').addEventListener('click', async () => {
    const parts = Array.from(document.querySelectorAll('input.p:checked')).map((c) => c.value);
    if (!parts.length) { $('msg').textContent = 'Pilih minimal satu part.'; return; }
    const btn = $('go');
    btn.disabled = true; btn.textContent = 'Memproses...';
    try {
      const payload = { name: styleName, data: styleB64, parts, mode: $('mode').value,
                        fix_intro_ending: $('fix-ie').checked || undefined,
                        template_name: $('tpl-select').value || undefined };
      if (fileMeta) payload.template = await b64(fileMeta);
      const res = await post('/api/repair', payload);

      // unduh otomatis
      const bytes = Uint8Array.from(atob(res.data), (c) => c.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], { type: 'application/octet-stream' }));
      const a = document.createElement('a');
      a.href = url; a.download = res.filename; a.click();
      URL.revokeObjectURL(url);

      $('msg').textContent = '';
      renderReport(res.report, res.filename);
    } catch (err) {
      $('msg').textContent = err.message;
    } finally {
      btn.disabled = false; btn.textContent = 'Perbaiki Style';
    }
  });

  function renderReport(rep, filename) {
    $('report-panel').hidden = false;
    const rows = rep.parts.map((p) => {
      const tag = p.status === 'ok'
        ? (p.truncated ? '<span class="warn-tag">terpotong</span>'
          : (p.grown_bars ? `<span class="warn-tag">dilebarkan +${p.grown_bars} bar</span>` : '<span class="ok-tag">ok</span>'))
        : `<span class="no-tag">${p.status.replace(/_/g, ' ')}</span>`;
      return `<tr>
        <td>${p.label}</td>
        <td class="muted">${p.target_section || '—'} ← ${p.template_section || '—'}</td>
        <td class="muted small">${p.casm === 'template' ? 'channel+voice ikut template' : (p.remap && p.remap.length ? 'dipindah: ' + p.remap.join(', ') : '—')}</td>
        <td class="num">${p.target_bars ?? '—'} / ${p.template_bars ?? '—'}</td>
        <td class="num">${p.notes_in}</td>
        <td>${tag}</td>
      </tr>`;
    }).join('');
    let fxHtml = '';
    const fx = rep.intro_ending;
    if (fx && fx.sections) {
      const fr = fx.sections.map((s) => {
        if (s.status) return `<tr><td>${s.section}</td><td colspan="3" class="muted">${s.status}</td></tr>`;
        return (s.parts || []).map((p) => `<tr>
          <td>${s.section}</td><td>${p.part}</td>
          <td class="muted">${p.channel !== undefined ? 'ch' + (p.channel + 1) : '—'}</td>
          <td class="muted small">${p.old ? p.old.join('/') + ' → ' + p.new.join('/') : (p.status || '')}</td></tr>`).join('');
      }).join('');
      fxHtml = `<h3 class="fx-title">🧩 Rapikan Intro 1–3 &amp; Ending 1</h3>
        <p class="muted small">Bass: kit ikut Main A + filter/EQ di-reset (harmonic 0, brightness 0, EQ high 0, EQ low +20). Rhythm1: kit ikut Fill In A. Rhythm2: kit ikut Main A. Nilai voice = MSB/LSB/PC.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Section</th><th>Part</th><th>Channel</th><th>Voice (lama → baru)</th></tr></thead>
          <tbody>${fr}</tbody>
        </table></div>`;
    }
    $('report').innerHTML = `
      <p class="file-ok">✅ Selesai — file <b>${filename}</b> (${(rep.output_bytes / 1024).toFixed(1)} KB) terunduh dengan nama aslinya.</p>
      <p class="muted small">Tersimpan juga di folder <code>out/</code> (nama sama) + arsip <code>out/arsip/</code>. Template: ${rep.template_source} · mode: ${rep.mode}</p>
      <div class="table-wrap"><table>
        <thead><tr><th>Part</th><th>Section (target ← template)</th><th>Penyesuaian channel</th><th class="num">Bar</th><th class="num">Note masuk</th><th>Status</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
      ${fxHtml}`;
    $('report-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
})();
