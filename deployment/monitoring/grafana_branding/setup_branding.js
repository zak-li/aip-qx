/**
 * Pex – Grafana branding setup
 *
 * What this script does:
 *  1. Diagnoses current state on the VM
 *  2. Configures grafana.ini (app_name, login titles)
 *  3. Uploads the Pex SVG icon and replaces all logo assets
 *  4. Patches index.html to inject custom CSS + "Powered by Grafana" footer
 *  5. Restarts grafana-server
 *
 * The script avoids touching JS bundles (fragile / cache-busted every upgrade).
 * All branding is done through stable entry points: grafana.ini + index.html template.
 */

'use strict';

const { Client } = require('ssh2');
const fs = require('fs');
const path = require('path');

// ── Connection config ─────────────────────────────────────────────────────────
const SSH = { host: '10.10.10.150', port: 22, username: 'zakaria', password: process.env.SSH_PASSWORD || 'zakaria' };
const SUDO = `echo '${SSH.password}' | sudo -S`;

// ── Local assets ──────────────────────────────────────────────────────────────
const ICON_SVG_PATH = path.resolve(__dirname, '../../../.github/assets/vector/icon.svg');

// ── CSS injected into index.html ──────────────────────────────────────────────
// Hides the default Grafana sidemenu footer logo text and adds our fixed badge.
const CUSTOM_CSS = `
  /* ── Pex custom branding ─────────────────────────────────── */

  /* Hide the Grafana wordmark that appears in the top-left nav */
  [class*="sidemenu"] [class*="logoText"],
  [class*="NavBar"] [class*="logoText"],
  .css-sidebar-logo-text,
  [data-testid="grafana-wordmark"] { display: none !important; }

  /* "Powered by Grafana" badge – bottom-right corner, always visible */
  #pex-powered-badge {
    position: fixed;
    bottom: 8px;
    right: 12px;
    z-index: 99999;
    font-size: 11px;
    color: rgba(180,180,180,0.75);
    font-family: Inter, Helvetica, Arial, sans-serif;
    letter-spacing: 0.02em;
    pointer-events: none;
    user-select: none;
  }
  #pex-powered-badge a {
    color: inherit;
    text-decoration: none;
  }
  #pex-powered-badge a:hover { color: #f46800; }

  /* Login page: replace Grafana logo area text */
  [class*="loginLogo"] + h1,
  [class*="login"] h1 { font-size: 0; }
  [class*="login"] h1::after { content: "Pex"; font-size: 24px; }
`.trim();

// ── HTML badge injected just before </body> ───────────────────────────────────
const BADGE_HTML = `<div id="pex-powered-badge">Powered by <a href="https://grafana.com" target="_blank" rel="noopener">Grafana</a></div>`;

// ── grafana.ini snippet (appended / merged) ───────────────────────────────────
// We write an override file to /etc/grafana/grafana.ini.d/ if the directory
// exists, otherwise we patch /etc/grafana/grafana.ini directly.
const INI_BLOCK = `
[server]
# Custom app name shown in browser tab and login page
app_name = Pex

[auth]
login_title = Pex – Regulatory Intelligence Platform

[users]
# Keeps the welcome e-mail subject branded
default_theme = dark
`.trim();

// ─────────────────────────────────────────────────────────────────────────────

function run() {
  const conn = new Client();

  conn.on('ready', () => {
    console.log('\n[SSH] Connected to', SSH.host);
    runDiagnostics(conn);
  });

  conn.on('error', (err) => {
    console.error('[SSH] Connection error:', err.message);
    process.exit(1);
  });

  conn.connect(SSH);
}

// ── Step 1: diagnose ──────────────────────────────────────────────────────────
function runDiagnostics(conn) {
  console.log('\n[1/5] Running diagnostics…');
  const cmd = `
    echo "=== GRAFANA VERSION ===" && (grafana-server --version 2>/dev/null || grafana server --version 2>/dev/null || dpkg -l grafana 2>/dev/null | grep '^ii' | awk '{print $2,$3}')
    echo "=== INDEX.HTML LOCATION ===" && ls -lh /usr/share/grafana/public/views/index.html 2>/dev/null || echo "NOT FOUND"
    echo "=== GRAFANA.INI ===" && ls -lh /etc/grafana/grafana.ini 2>/dev/null || echo "NOT FOUND"
    echo "=== IMG DIR ===" && ls /usr/share/grafana/public/img/ | grep -E "grafana|logo|fav|apple" | head -20
    echo "=== CURRENT APP_NAME ===" && grep -i "app_name" /etc/grafana/grafana.ini 2>/dev/null || echo "(not set)"
  `;
  execCmd(conn, cmd, (output) => {
    console.log(output);
    uploadIconAndPatch(conn);
  });
}

// ── Step 2 & 3: upload icon + patch logos ─────────────────────────────────────
function uploadIconAndPatch(conn) {
  console.log('\n[2/5] Uploading Pex icon to VM…');

  if (!fs.existsSync(ICON_SVG_PATH)) {
    console.error('[ERROR] Icon not found at:', ICON_SVG_PATH);
    applyIniConfig(conn);
    return;
  }

  conn.sftp((err, sftp) => {
    if (err) { console.error('[SFTP] Error:', err.message); applyIniConfig(conn); return; }

    const writeStream = sftp.createWriteStream('/tmp/pex_icon.svg');
    writeStream.on('close', () => {
      console.log('[SFTP] Icon uploaded to /tmp/pex_icon.svg');
      replaceLogos(conn);
    });
    writeStream.on('error', (e) => {
      console.error('[SFTP] Write error:', e.message);
      replaceLogos(conn);
    });
    fs.createReadStream(ICON_SVG_PATH).pipe(writeStream);
  });
}

function replaceLogos(conn) {
  console.log('\n[3/5] Replacing Grafana logos with Pex icon…');
  // Target every known logo/favicon location in Grafana public assets
  const cmd = `
    ICON=/tmp/pex_icon.svg
    IMG=/usr/share/grafana/public/img

    # Main SVG logos
    ${SUDO} cp $ICON $IMG/grafana_icon.svg
    ${SUDO} cp $ICON $IMG/grafana_com_auth_icon.svg
    ${SUDO} find $IMG -name "grafana_*.svg" -exec cp $ICON {} \\;
    ${SUDO} find $IMG -name "*logo*.svg" -exec cp $ICON {} \\;
    ${SUDO} find /usr/share/grafana/public -name "g8_home*.svg" -exec cp $ICON {} \\;
    ${SUDO} find /usr/share/grafana/public -name "grafana-logo*.svg" -exec cp $ICON {} \\;

    # PNG favicons – convert SVG → PNG if ImageMagick is available
    if command -v convert >/dev/null 2>&1; then
      ${SUDO} convert -background none -resize 32x32   $ICON $IMG/fav32.png
      ${SUDO} convert -background none -resize 64x64   $ICON $IMG/fav64.png
      ${SUDO} convert -background none -resize 152x152 $ICON $IMG/apple-touch-icon.png
      echo "PNG favicons generated via ImageMagick"
    elif command -v rsvg-convert >/dev/null 2>&1; then
      ${SUDO} rsvg-convert -w 32 -h 32   $ICON -o $IMG/fav32.png
      ${SUDO} rsvg-convert -w 152 -h 152 $ICON -o $IMG/apple-touch-icon.png
      echo "PNG favicons generated via rsvg-convert"
    else
      echo "WARNING: no SVG-to-PNG converter found; PNG favicons unchanged"
    fi

    echo "Logo replacement done"
  `;
  execCmd(conn, cmd, (output) => {
    console.log(output);
    applyIniConfig(conn);
  });
}

// ── Step 4a: grafana.ini ──────────────────────────────────────────────────────
function applyIniConfig(conn) {
  console.log('\n[4/5] Applying grafana.ini branding settings…');

  // Write the INI block to a temp file then merge it
  const tmpIni = '/tmp/pex_branding.ini';
  const iniEscaped = INI_BLOCK.replace(/'/g, "'\\''");

  const cmd = `
    # Write the branding snippet
    cat > ${tmpIni} << 'INIEOF'
${INI_BLOCK}
INIEOF

    INI=/etc/grafana/grafana.ini

    # Remove any previous Pex blocks to avoid duplicates
    ${SUDO} sed -i '/# Pex branding start/,/# Pex branding end/d' $INI

    # Patch [server] section: replace or append app_name
    if grep -q "^app_name" $INI; then
      ${SUDO} sed -i 's/^app_name.*/app_name = Pex/' $INI
    elif grep -q "^\\[server\\]" $INI; then
      ${SUDO} sed -i '/^\\[server\\]/a app_name = Pex' $INI
    else
      echo "" | ${SUDO} tee -a $INI
      echo "[server]" | ${SUDO} tee -a $INI
      echo "app_name = Pex" | ${SUDO} tee -a $INI
    fi

    # Patch login_title under [auth]
    if grep -q "^login_title" $INI; then
      ${SUDO} sed -i 's/^login_title.*/login_title = Pex – Regulatory Intelligence Platform/' $INI
    fi

    echo "grafana.ini updated"
    grep -E "app_name|login_title" $INI | head -5
  `;
  execCmd(conn, cmd, (output) => {
    console.log(output);
    patchIndexHtml(conn);
  });
}

// ── Step 4b: index.html injection ────────────────────────────────────────────
function patchIndexHtml(conn) {
  console.log('\n[4b/5] Patching index.html with custom CSS + Powered-by badge…');

  const INDEX = '/usr/share/grafana/public/views/index.html';

  // We write the CSS and badge via heredoc, then sed-inject before </head> and </body>
  // Using Python for reliable multi-line patching (always available on Ubuntu)
  const pythonScript = `
import re, sys

with open('${INDEX}', 'r', encoding='utf-8') as f:
    html = f.read()

STYLE_TAG = """<style id="pex-custom">
${CUSTOM_CSS.replace(/`/g, '\\`').replace(/\$/g, '\\$').replace(/\\/g, '\\\\')}
</style>"""

BADGE_TAG = """${BADGE_HTML}"""

# Remove previous injections to keep idempotent
html = re.sub(r'<style id="pex-custom">.*?</style>', '', html, flags=re.DOTALL)
html = re.sub(r'<div id="pex-powered-badge">.*?</div>', '', html)

# Inject style before </head>
html = html.replace('</head>', STYLE_TAG + '\\n</head>', 1)

# Inject badge before </body>
html = html.replace('</body>', BADGE_TAG + '\\n</body>', 1)

with open('${INDEX}', 'w', encoding='utf-8') as f:
    f.write(html)

print("index.html patched successfully")
`.trim();

  // Escape for shell here-doc
  const cmd = `
    # Backup original if not already backed up
    [ -f ${INDEX}.orig ] || ${SUDO} cp ${INDEX} ${INDEX}.orig

    ${SUDO} python3 - << 'PYEOF'
import re

INDEX = '${INDEX}'

STYLE = """<style id="pex-custom">
/* Pex custom branding */
[class*="sidemenu"] [class*="logoText"],
[class*="NavBar"] [class*="logoText"],
.css-sidebar-logo-text,
[data-testid="grafana-wordmark"] { display: none !important; }

#pex-powered-badge {
  position: fixed;
  bottom: 8px;
  right: 12px;
  z-index: 99999;
  font-size: 11px;
  color: rgba(180,180,180,0.75);
  font-family: Inter, Helvetica, Arial, sans-serif;
  letter-spacing: 0.02em;
  pointer-events: none;
  user-select: none;
}
#pex-powered-badge a { color: inherit; text-decoration: none; }
#pex-powered-badge a:hover { color: #f46800; }
</style>"""

BADGE = '<div id="pex-powered-badge">Powered by <a href="https://grafana.com" target="_blank" rel="noopener">Grafana</a></div>'

with open(INDEX, 'r', encoding='utf-8') as f:
    html = f.read()

# Remove previous injections (idempotent)
html = re.sub(r'<style id="pex-custom">.*?</style>', '', html, flags=re.DOTALL)
html = re.sub(r'<div id="pex-powered-badge">.*?</div>', '', html)

# Inject
if '</head>' in html:
    html = html.replace('</head>', STYLE + '\\n</head>', 1)
else:
    print("WARNING: </head> not found in index.html")

if '</body>' in html:
    html = html.replace('</body>', BADGE + '\\n</body>', 1)
else:
    print("WARNING: </body> not found in index.html")

with open(INDEX, 'w', encoding='utf-8') as f:
    f.write(html)

print("index.html patched OK")
PYEOF
  `;

  execCmd(conn, cmd, (output) => {
    console.log(output);
    restartGrafana(conn);
  });
}

// ── Step 5: restart ───────────────────────────────────────────────────────────
function restartGrafana(conn) {
  console.log('\n[5/5] Restarting Grafana…');
  const cmd = `
    ${SUDO} systemctl restart grafana-server
    sleep 3
    ${SUDO} systemctl is-active grafana-server
    echo "--- Verify index.html injection ---"
    grep -c "pex-custom" /usr/share/grafana/public/views/index.html && echo "CSS block present" || echo "CSS block MISSING"
    grep -c "pex-powered-badge" /usr/share/grafana/public/views/index.html && echo "Badge present" || echo "Badge MISSING"
    echo "--- Done ---"
  `;
  execCmd(conn, cmd, (output) => {
    console.log(output);
    console.log('\n✓ Branding setup complete. Open http://10.10.10.150:3000 in your browser.');
    console.log('  • Logo:            replaced in /usr/share/grafana/public/img/');
    console.log('  • App title:       "Pex" (grafana.ini app_name)');
    console.log('  • Footer badge:    "Powered by Grafana" (bottom-right)');
    console.log('  If the browser still shows old logos, hard-refresh with Ctrl+Shift+R.\n');
    conn.end();
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function execCmd(conn, cmd, callback) {
  conn.exec(cmd, (err, stream) => {
    if (err) { console.error('[exec] Error:', err.message); callback(''); return; }
    let out = '';
    stream
      .on('close', () => callback(out))
      .on('data', (d) => { out += d; process.stdout.write(d); })
      .stderr.on('data', (d) => { out += d; process.stderr.write('[stderr] ' + d); });
  });
}

run();
