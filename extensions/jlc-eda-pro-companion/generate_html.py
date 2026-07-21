"""Generate iframe/service-not-found.html with embedded base64 scripts."""
import base64, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

with open('bridge_server/start_server.bat', 'rb') as f:
    bat_b64 = base64.b64encode(f.read()).decode()

with open('bridge_server/start_server.sh', 'rb') as f:
    sh_b64 = base64.b64encode(f.read()).decode()

html = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>JLCEDA Design Companion</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { height: 100%; overflow: hidden; }
body {
  font-family: 'Segoe UI', 'Microsoft YaHei', -apple-system, sans-serif;
  font-size: 13px;
  background: #F5F5F5;
  color: #333;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.icon { font-size: 40px; margin-bottom: 12px; }
.title { font-size: 16px; font-weight: 600; margin-bottom: 8px; color: #222; }
.desc { color: #666; text-align: center; line-height: 1.6; margin-bottom: 12px; max-width: 400px; }
.steps { color: #555; text-align: left; line-height: 2.0; margin-bottom: 16px; max-width: 400px; font-size: 12px; }
.btn-group { display: flex; flex-direction: column; align-items: stretch; gap: 8px; margin-bottom: 16px; width: 280px; }
.btn {
  padding: 7px 16px;
  font-size: 12px;
  border: 1px solid #D0D0D0;
  border-radius: 4px;
  background: #FFF;
  color: #333;
  cursor: pointer;
  white-space: nowrap;
}
.btn:hover { background: #F0F0F0; border-color: #007AFF; color: #007AFF; }
.btn-download {
  background: #34C759;
  border-color: #34C759;
  color: #FFF;
  padding: 8px 20px;
  font-size: 13px;
}
.btn-download:hover { background: #2DB84D; border-color: #2DB84D; color: #FFF; }
.dl-group { display: flex; gap: 6px; }
.dl-group .btn-download { flex: 1; font-size: 11px; padding: 7px 8px; text-align: center; }
.dl-label { font-size: 11px; color: #888; margin: 2px 0 -2px 2px; }
.btn-python {
  background: #3776AB;
  border-color: #3776AB;
  color: #FFF;
  padding: 8px 20px;
  font-size: 13px;
}
.btn-python:hover { background: #2D5F8A; border-color: #2D5F8A; color: #FFF; }
.btn-primary {
  background: #007AFF;
  border-color: #007AFF;
  color: #FFF;
  padding: 8px 20px;
  font-size: 13px;
  border-radius: 4px;
}
.btn-primary:hover { background: #0066DD; border-color: #0066DD; color: #FFF; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.status { font-size: 11px; color: #999; margin-top: 8px; min-height: 16px; }
.status.error { color: #c0392b; }
.status.success { color: #27ae60; }
</style>
</head>
<body>
<div class="icon">&#x26A0;&#xFE0F;</div>
<div class="title" id="titleText"></div>
<div class="desc" id="descText"></div>
<div class="steps" id="stepsText"></div>

<div class="btn-group">
  <button class="btn btn-python" onclick="openPython()" id="btnPython"></button>
  <div class="dl-label" id="dlLabel"></div>
  <div class="dl-group">
    <button class="btn btn-download" onclick="downloadScript('windows')" id="btnDownloadWin"></button>
    <button class="btn btn-download" onclick="downloadScript('linux')" id="btnDownloadLinux"></button>
    <button class="btn btn-download" onclick="downloadScript('macos')" id="btnDownloadMac"></button>
  </div>
  <button class="btn btn-primary" onclick="retry()" id="btnRetry"></button>
</div>
<div class="status" id="statusText"></div>

<script>
(function() {
  'use strict';
  var MSG_PREFIX = 'jlc-eda-design-companion.';
  var SCRIPTS = {
    windows: { b64: '%%BAT_B64%%', filename: 'start_server.bat', zipname: 'jlc-eda-companion-bridge-windows.zip' },
    linux:   { b64: '%%SH_B64%%', filename: 'start_server.sh', zipname: 'jlc-eda-companion-bridge-linux.zip' },
    macos:   { b64: '%%SH_B64%%', filename: 'start_server.sh', zipname: 'jlc-eda-companion-bridge-macos.zip' }
  };

  function decodeBase64(b64) {
    var bin = atob(b64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes;
  }

  var edaObj = (typeof eda !== 'undefined') ? eda : (window.parent && window.parent.eda);
  function t(tag) {
    if (edaObj && edaObj.sys_I18n) return edaObj.sys_I18n.text(tag);
    return tag;
  }

  function applyI18n() {
    document.getElementById('titleText').textContent = t('JLCEDA Design Companion Bridge Not Running');
    document.getElementById('descText').textContent = t('Please follow these steps to start the bridge server:');
    document.getElementById('stepsText').innerText = t('1. Download and install Python 3.10+ (skip if installed)\n2. Download the startup script ZIP for your OS, extract it, then run\n3. Click "Retry" after the service starts successfully');
    document.getElementById('btnPython').textContent = t('1. Install Python');
    document.getElementById('dlLabel').textContent = t('2. Download Script:');
    document.getElementById('btnDownloadWin').textContent = 'Windows';
    document.getElementById('btnDownloadLinux').textContent = 'Linux';
    document.getElementById('btnDownloadMac').textContent = 'macOS';
    document.getElementById('btnRetry').textContent = t('3. Retry');
    document.title = t('JLCEDA Design Companion Bridge Not Running');
  }

  applyI18n();

  function getEda() {
    try {
      if (window.parent && window.parent.eda) return window.parent.eda;
      if (window.top && window.top.eda) return window.top.eda;
      if (window.eda) return window.eda;
    } catch (e) {}
    return null;
  }

  function publish(topic, data) {
    var e = getEda();
    if (!e || !e.sys_MessageBus) return;
    var fullTopic = MSG_PREFIX + topic;
    if (typeof e.sys_MessageBus.publish === 'function') {
      e.sys_MessageBus.publish(fullTopic, JSON.stringify(data || {}));
    } else if (typeof e.sys_MessageBus.push === 'function') {
      e.sys_MessageBus.push(fullTopic, JSON.stringify(data || {}));
    }
  }

  function subscribe(topic, handler) {
    var e = getEda();
    if (!e || !e.sys_MessageBus) return;
    var fullTopic = MSG_PREFIX + topic;
    e.sys_MessageBus.subscribe(fullTopic, function(msg) {
      try { handler(typeof msg === 'string' ? JSON.parse(msg) : msg); }
      catch (err) {}
    });
  }

  subscribe('retry-result', function(data) {
    var statusEl = document.getElementById('statusText');
    var btn = document.getElementById('btnRetry');
    btn.disabled = false;
    if (data && data.success) {
      statusEl.textContent = t('Connected! Opening routing tool...');
      statusEl.className = 'status success';
    } else {
      statusEl.textContent = t('Service not detected, please confirm it is running');
      statusEl.className = 'status error';
    }
  });

  window.openPython = function() {
    var e = getEda();
    if (e && e.sys_Window) {
      e.sys_Window.open('https://www.python.org/downloads/');
    }
  };

  window.downloadScript = function(os) {
    var info = SCRIPTS[os];
    if (!info) return;
    var dataBytes = decodeBase64(info.b64);
    var isUnix = (os === 'linux' || os === 'macos');
    var blob = buildZip(info.filename, dataBytes, isUnix);
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = info.zipname;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
    var statusEl = document.getElementById('statusText');
    statusEl.className = 'status success';
    statusEl.textContent = t('Downloaded. Extract and run the script.');
  };

  function buildZip(filename, dataBytes, executable) {
    var enc = new TextEncoder();
    var nameBytes = enc.encode(filename);
    var crc = crc32(dataBytes);
    // Unix external attributes: 0755 for executable, 0644 for regular
    var extAttr = executable ? ((0x81ED << 16) >>> 0) : ((0x81A4 << 16) >>> 0);

    var localHeader = new ArrayBuffer(30);
    var lh = new DataView(localHeader);
    lh.setUint32(0, 0x04034b50, true);
    lh.setUint16(4, 20, true);
    lh.setUint16(6, 0, true);
    lh.setUint16(8, 0, true);
    lh.setUint16(10, 0, true);
    lh.setUint16(12, 0, true);
    lh.setUint32(14, crc, true);
    lh.setUint32(18, dataBytes.length, true);
    lh.setUint32(22, dataBytes.length, true);
    lh.setUint16(26, nameBytes.length, true);
    lh.setUint16(28, 0, true);

    var central = new ArrayBuffer(46);
    var cd = new DataView(central);
    cd.setUint32(0, 0x02014b50, true);
    cd.setUint16(4, 0x0314, true);  // version made by: Unix (03) + ZIP 2.0 (14)
    cd.setUint16(6, 20, true);
    cd.setUint16(8, 0, true);
    cd.setUint16(10, 0, true);
    cd.setUint16(12, 0, true);
    cd.setUint16(14, 0, true);
    cd.setUint32(16, crc, true);
    cd.setUint32(20, dataBytes.length, true);
    cd.setUint32(24, dataBytes.length, true);
    cd.setUint16(28, nameBytes.length, true);
    cd.setUint16(30, 0, true);
    cd.setUint16(32, 0, true);
    cd.setUint16(34, 0, true);
    cd.setUint16(36, 0, true);
    cd.setUint32(38, extAttr, true);
    cd.setUint32(42, 0, true);

    var localSize = 30 + nameBytes.length + dataBytes.length;
    var centralSize = 46 + nameBytes.length;
    var eocd = new ArrayBuffer(22);
    var e = new DataView(eocd);
    e.setUint32(0, 0x06054b50, true);
    e.setUint16(4, 0, true);
    e.setUint16(6, 0, true);
    e.setUint16(8, 1, true);
    e.setUint16(10, 1, true);
    e.setUint32(12, centralSize, true);
    e.setUint32(16, localSize, true);
    e.setUint16(20, 0, true);

    return new Blob([
      localHeader, nameBytes, dataBytes,
      central, nameBytes,
      eocd
    ], { type: 'application/zip' });
  }

  var _crcTable = null;
  function crc32(bytes) {
    if (!_crcTable) {
      _crcTable = new Uint32Array(256);
      for (var i = 0; i < 256; i++) {
        var c = i;
        for (var j = 0; j < 8; j++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
        _crcTable[i] = c >>> 0;
      }
    }
    var crc = 0xFFFFFFFF;
    for (var i = 0; i < bytes.length; i++) crc = (_crcTable[(crc ^ bytes[i]) & 0xFF] ^ (crc >>> 8)) >>> 0;
    return (crc ^ 0xFFFFFFFF) >>> 0;
  }

  window.retry = function() {
    var statusEl = document.getElementById('statusText');
    var btn = document.getElementById('btnRetry');
    btn.disabled = true;
    statusEl.textContent = t('Detecting service...');
    statusEl.className = 'status';
    publish('retry-connection', {});
  };
})();
</script>
</body>
</html>'''

# Replace placeholders with actual base64
html = html.replace('%%BAT_B64%%', bat_b64)
html = html.replace('%%SH_B64%%', sh_b64)

with open('iframe/service-not-found.html', 'w', encoding='utf-8', newline='\n') as f:
    f.write(html)

print('OK: wrote', len(html), 'bytes to iframe/service-not-found.html')
