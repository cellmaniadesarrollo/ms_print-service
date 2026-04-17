# app/dashboard.py
"""
HTML del panel de administración del Print Service.
Se importa desde main.py y se sirve en la ruta GET /.
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Print Service — Panel</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg:       #0d0f12;
      --surface:  #151820;
      --border:   #252a35;
      --accent:   #00e5a0;
      --warn:     #f5a623;
      --danger:   #ff4d4d;
      --text:     #c8d0e0;
      --muted:    #5a6478;
      --mono:     'IBM Plex Mono', monospace;
      --sans:     'IBM Plex Sans', sans-serif;
    }

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: var(--sans);
      min-height: 100vh;
      padding: 32px 24px;
    }

    /* ── Header ── */
    header {
      display: flex;
      align-items: center;
      gap: 16px;
      margin-bottom: 40px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border);
    }
    .logo {
      width: 36px; height: 36px;
      background: var(--accent);
      border-radius: 6px;
      display: flex; align-items: center; justify-content: center;
      font-size: 18px; flex-shrink: 0;
    }
    header h1 {
      font-family: var(--mono);
      font-size: 1rem;
      font-weight: 600;
      letter-spacing: 0.05em;
      color: #fff;
    }
    header p {
      font-size: 0.75rem;
      color: var(--muted);
      font-family: var(--mono);
      margin-top: 2px;
    }
    .status-pill {
      margin-left: auto;
      display: flex;
      align-items: center;
      gap: 8px;
      background: #0a1f16;
      border: 1px solid #1a4a30;
      border-radius: 100px;
      padding: 6px 14px;
      font-family: var(--mono);
      font-size: 0.72rem;
      color: var(--accent);
      flex-shrink: 0;
    }
    .dot {
      width: 7px; height: 7px;
      border-radius: 50%;
      background: var(--accent);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50%       { opacity: 0.3; }
    }

    /* ── Layout ── */
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 16px;
      margin-bottom: 24px;
    }
    @media (max-width: 900px) { .grid { grid-template-columns: 1fr 1fr; } }
    @media (max-width: 580px) { .grid { grid-template-columns: 1fr; } }

    /* ── Cards ── */
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 20px 22px;
    }
    .card-label {
      font-family: var(--mono);
      font-size: 0.65rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 8px;
    }
    .card-value {
      font-family: var(--mono);
      font-size: 1.05rem;
      font-weight: 600;
      color: #fff;
    }
    .card-value.accent { color: var(--accent); }
    .card-value.warn   { color: var(--warn); }
    .card-sub {
      font-size: 0.72rem;
      color: var(--muted);
      margin-top: 4px;
      font-family: var(--mono);
    }

    /* ── Editor ── */
    .editor-wrap {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
    }
    .editor-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 20px;
      border-bottom: 1px solid var(--border);
      background: #111318;
    }
    .editor-title {
      font-family: var(--mono);
      font-size: 0.78rem;
      font-weight: 600;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .editor-title span { color: var(--muted); font-weight: 400; }
    .btn-group { display: flex; gap: 10px; }

    button {
      font-family: var(--mono);
      font-size: 0.72rem;
      font-weight: 500;
      padding: 7px 16px;
      border-radius: 6px;
      border: none;
      cursor: pointer;
      transition: opacity 0.15s, transform 0.1s;
      letter-spacing: 0.04em;
    }
    button:active { transform: scale(0.97); }
    .btn-primary  { background: var(--accent); color: #0d1a12; }
    .btn-secondary {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--muted);
    }
    .btn-secondary:hover { border-color: var(--text); color: var(--text); }
    button:disabled { opacity: 0.4; cursor: not-allowed; }

    #editor {
      width: 100%;
      min-height: 440px;
      background: #0d0f12;
      color: #a8d5b5;
      font-family: var(--mono);
      font-size: 0.82rem;
      line-height: 1.7;
      padding: 20px 24px;
      border: none;
      outline: none;
      resize: vertical;
      tab-size: 2;
      white-space: pre;
      overflow-x: auto;
    }
    #editor:focus { box-shadow: inset 0 0 0 2px #00e5a020; }

    /* ── Toast ── */
    #toast {
      position: fixed;
      bottom: 28px; right: 28px;
      padding: 12px 20px;
      border-radius: 8px;
      font-family: var(--mono);
      font-size: 0.75rem;
      font-weight: 500;
      max-width: 320px;
      opacity: 0;
      transform: translateY(12px);
      transition: opacity 0.25s, transform 0.25s;
      pointer-events: none;
      z-index: 100;
    }
    #toast.show { opacity: 1; transform: translateY(0); }
    #toast.ok   { background: #0a2a1a; border: 1px solid #1a5a30; color: var(--accent); }
    #toast.err  { background: #2a0a0a; border: 1px solid #5a1a1a; color: var(--danger); }
    #toast.warn { background: #2a1a00; border: 1px solid #5a3a00; color: var(--warn); }

    /* ── Footer ── */
    footer {
      margin-top: 32px;
      padding-top: 20px;
      border-top: 1px solid var(--border);
      font-family: var(--mono);
      font-size: 0.65rem;
      color: var(--muted);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
  </style>
</head>
<body>

<header>
  <div class="logo">🖨</div>
  <div>
    <h1>PRINT SERVICE</h1>
    <p id="uptime-label">calculando uptime...</p>
  </div>
  <div class="status-pill">
    <div class="dot"></div>
    ONLINE
  </div>
</header>

<div class="grid">
  <div class="card">
    <div class="card-label">Conexión</div>
    <div class="card-value accent" id="s-connection">—</div>
    <div class="card-sub" id="s-conn-detail">—</div>
  </div>
  <div class="card">
    <div class="card-label">Papel</div>
    <div class="card-value" id="s-paper">—</div>
    <div class="card-sub" id="s-encoding">—</div>
  </div>
  <div class="card">
    <div class="card-label">Último reload</div>
    <div class="card-value warn" id="s-reload">—</div>
    <div class="card-sub" id="s-uptime">—</div>
  </div>
</div>

<div class="editor-wrap">
  <div class="editor-header">
    <div class="editor-title">
      config.json <span id="config-path"></span>
    </div>
    <div class="btn-group">
      <button class="btn-secondary" onclick="reloadFromDisk()">↺ Recargar</button>
      <button class="btn-primary" id="save-btn" onclick="saveConfig()">Guardar y recargar</button>
    </div>
  </div>
  <textarea id="editor" spellcheck="false"></textarea>
</div>

<footer>
  <span>Print Service v1.1.0 — FastAPI + uvicorn</span>
  <span id="footer-port"></span>
</footer>

<div id="toast"></div>

<script>
  const port = location.port || (location.protocol === 'https:' ? 443 : 80);
  document.getElementById('footer-port').textContent = `https://localhost:${port}`;

  async function fetchStatus() {
    try {
      const r = await fetch('/api/status');
      const d = await r.json();
      document.getElementById('s-connection').textContent = d.connection.toUpperCase();
      document.getElementById('s-conn-detail').textContent =
        d.connection === 'network'
          ? `${d.network_ip}:${d.network_port}`
          : `VID:${d.usb_vid}  PID:${d.usb_pid}`;
      document.getElementById('s-paper').textContent    = `${d.paper_width_mm}mm / ${d.paper_px}px`;
      document.getElementById('s-encoding').textContent = `encoding: ${d.encoding}`;
      document.getElementById('s-reload').textContent   = d.last_reload;
      document.getElementById('s-uptime').textContent   = `uptime: ${formatUptime(d.uptime_seconds)}`;
      document.getElementById('config-path').textContent = d.config_path;
      document.getElementById('uptime-label').textContent = `uptime ${formatUptime(d.uptime_seconds)}`;
      document.getElementById('s-version').textContent = d.version;
    } catch(e) { console.warn('Status fetch failed', e); }
  }

  function formatUptime(secs) {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = Math.floor(secs % 60);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }

  async function reloadFromDisk() {
    try {
      const r = await fetch('/api/config');
      document.getElementById('editor').value = await r.text();
      toast('Config recargado desde disco', 'ok');
    } catch(e) { toast('Error al cargar config', 'err'); }
  }

  async function saveConfig() {
    const raw = document.getElementById('editor').value;
    try { JSON.parse(raw); }
    catch(e) { toast(`JSON inválido: ${e.message}`, 'err'); return; }

    const btn = document.getElementById('save-btn');
    btn.disabled = true;
    btn.textContent = 'Guardando...';

    try {
      const r = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw })
      });
      const d = await r.json();
      if (d.success) {
        toast('✓ Config guardado y recargado correctamente', 'ok');
        await fetchStatus();
      } else {
        toast(`Error: ${d.message}`, 'err');
      }
    } catch(e) {
      toast('Error al guardar', 'err');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Guardar y recargar';
    }
  }

  let _toastTimer;
  function toast(msg, type = 'ok') {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = `show ${type}`;
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => { el.className = ''; }, 3500);
  }

  document.getElementById('editor').addEventListener('keydown', e => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const el = e.target, s = el.selectionStart;
      el.value = el.value.substring(0, s) + '  ' + el.value.substring(el.selectionEnd);
      el.selectionStart = el.selectionEnd = s + 2;
    }
  });

  fetchStatus();
  reloadFromDisk();
  setInterval(fetchStatus, 5000);
</script>
</body>
</html>"""