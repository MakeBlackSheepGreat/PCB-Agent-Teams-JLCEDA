(function() {
  'use strict';

  var eda = window.eda;
  var MSG_PREFIX = 'kirouting-integration.';
  var MM_TO_MIL = 1.0 / 0.0254;

  // State
  var allNets = [];
  var allComponents = [];
  var allLayers = [];
  var selectedNets = {};
  var routingInProgress = false;

  function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function _id(id) { return document.getElementById(id); }
  function _num(id) { var el = _id(id); return el ? parseFloat(el.value) : undefined; }
  function _val(id) { var el = _id(id); return el ? (el.type === 'checkbox' ? el.checked : el.value) : undefined; }

  // ─── MessageBus ───

  function sendToExt(topic, data) {
    var fullTopic = MSG_PREFIX + topic;
    if (eda && eda.sys_MessageBus) {
      if (typeof eda.sys_MessageBus.publish === 'function') {
        eda.sys_MessageBus.publish(fullTopic, JSON.stringify(data || {}));
      } else if (typeof eda.sys_MessageBus.push === 'function') {
        eda.sys_MessageBus.push(fullTopic, JSON.stringify(data || {}));
      }
    }
  }

  function onExtMessage(topic, handler) {
    var fullTopic = MSG_PREFIX + topic;
    if (eda && eda.sys_MessageBus) {
      eda.sys_MessageBus.subscribe(fullTopic, function(msg) {
        try {
          handler(typeof msg === 'string' ? JSON.parse(msg) : msg);
        } catch (e) {
          console.error('MessageBus parse error:', e);
        }
      });
    }
  }

  // ─── Init ───

  function onLoad() {
    loadSettings();
    bindEvents();
    subscribeMessages();
    loadData();
  }

  function loadData() {
    sendToExt('get-nets', {});
    sendToExt('get-components', {});
    sendToExt('get-layers', {});
  }

  function subscribeMessages() {
    onExtMessage('nets-list', function(data) {
      allNets = data.nets || [];
      renderNetList();
      updateStatusBar();
    });

    onExtMessage('components-list', function(data) {
      allComponents = data.components || [];
      renderComponentDropdown();
    });

    onExtMessage('layers-list', function(data) {
      allLayers = data.layers || [];
      renderLayerCheckboxes();
    });

    onExtMessage('routing-progress', function(data) {
      setProgress(data.percent || 0);
      setStatus(data.message || 'Routing...');
    });

    onExtMessage('routing-complete', function(data) {
      if (data.error) {
        setProgress(0);
        setStatus('Failed: ' + data.error);
      } else {
        var s = data.stats || {};
        setProgress(100);
        setStatus('Done: ' + (s.nets_routed || 0) + ' nets routed, ' +
          (s.tracks_added || 0) + ' tracks, ' +
          (s.vias_added || 0) + ' vias (' +
          (s.time_seconds || 0).toFixed(1) + 's)');
      }
      finishRouting();
    });
  }

  // ─── Rendering ───

  function isDiffPairName(name) {
    return /[_+](P|N|POS|NEG|PLUS|MINUS)$/i.test(name) || /[_+](P|N)\d*$/i.test(name);
  }

  function renderNetList() {
    var list = _id('net-list');
    if (!list) return;
    var filter = (_id('net-filter') || {}).value || '';
    filter = filter.toLowerCase();
    var compFilter = (_id('comp-filter') || {}).value || '';
    compFilter = compFilter.toLowerCase();
    var hideConnected = _id('hide-connected');
    hideConnected = hideConnected ? hideConnected.checked : false;
    var hideDiff = _id('hide-differential');
    hideDiff = hideDiff ? hideDiff.checked : false;
    var compSel = (_id('component-select') || {}).value || '';

    var filtered = allNets.filter(function(n) {
      if (filter && n.name.toLowerCase().indexOf(filter) < 0) return false;
      if (hideConnected && n.isConnected) return false;
      if (hideDiff && isDiffPairName(n.name)) return false;
      if (compFilter && !(n.components || []).some(function(c) { return c.toLowerCase().indexOf(compFilter) >= 0; })) return false;
      if (compSel && !(n.components || []).some(function(c) { return c === compSel; })) return false;
      return true;
    });

    list.innerHTML = '';
    filtered.forEach(function(n) {
      var div = document.createElement('div');
      var isSel = !!selectedNets[n.name];
      div.className = 'net-item' + (n.isConnected ? ' connected' : '') + (isSel ? ' selected' : '');
      div.innerHTML = '<span class="net-check">' + (isSel ? '✓' : '') + '</span>' +
        '<span class="net-name">' + esc(n.name) + '</span>';
      (function(name) {
        div.addEventListener('click', function() {
          toggleNet(name, !selectedNets[name]);
        });
      })(n.name);
      list.appendChild(div);
    });

    updateStatusBar();
  }

  function toggleNet(name, checked) {
    if (checked) selectedNets[name] = true; else delete selectedNets[name];
    renderNetList();
    saveSettings();
  }

  function renderComponentDropdown() {
    var sel = _id('component-select');
    if (!sel) return;
    var val = sel.value;
    sel.innerHTML = '<option value="">(none)</option>';
    allComponents.filter(function(c) { return c.padCount >= 2; })
      .sort(function(a, b) { return b.padCount - a.padCount; })
      .forEach(function(c) {
        var opt = document.createElement('option');
        opt.value = c.designator;
        opt.textContent = c.designator + ' (' + c.padCount + ' pads)';
        sel.appendChild(opt);
      });
    sel.value = val;
  }

  function renderLayerCheckboxes() {
    var container = _id('layer-checkboxes');
    if (!container) return;
    container.innerHTML = '';
    allLayers.forEach(function(l) {
      var label = document.createElement('label');
      label.innerHTML = '<input type="checkbox" checked data-layer-id="' + l.id + '"> ' + esc(l.name);
      container.appendChild(label);
    });
  }

  function updateStatusBar() {
    var bar = _id('status-bar');
    if (!bar) return;
    var total = allNets.length;
    var conn = allNets.filter(function(n) { return n.isConnected; }).length;
    var sel = Object.keys(selectedNets).length;
    bar.textContent = 'Total: ' + total + ' | Connected: ' + conn + ' | To route: ' + (total - conn) + ' | Selected: ' + sel;
  }

  // ─── Events ───

  function bindEvents() {
    var nf = _id('net-filter');
    if (nf) nf.addEventListener('input', renderNetList);
    var cf = _id('comp-filter');
    if (cf) cf.addEventListener('input', renderNetList);
    var hc = _id('hide-connected');
    if (hc) hc.addEventListener('change', renderNetList);
    var hd = _id('hide-differential');
    if (hd) hd.addEventListener('change', renderNetList);
    var cs = _id('component-select');
    if (cs) cs.addEventListener('change', renderNetList);

    _id('btn-select-all').addEventListener('click', function() {
      document.querySelectorAll('#net-list .net-item').forEach(function(div) {
        var name = div.querySelector('.net-name').textContent;
        selectedNets[name] = true;
      });
      renderNetList();
      saveSettings();
    });
    _id('btn-select-none').addEventListener('click', function() {
      selectedNets = {};
      renderNetList();
      saveSettings();
    });

    _id('btn-route').addEventListener('click', startRouting);
    _id('btn-cancel').addEventListener('click', function() {
      if (routingInProgress) {
        cancelRouting();
      }
    });
  }

  // ─── Routing ───

  function startRouting() {
    var netsToRoute = Object.keys(selectedNets);
    if (netsToRoute.length === 0) {
      setStatus('Check nets to include in operation (Ctrl+A to select all highlighted)');
      return;
    }

    var selectedLayers = [];
    document.querySelectorAll('#layer-checkboxes input[type="checkbox"]:checked').forEach(function(cb) {
      selectedLayers.push(parseInt(cb.getAttribute('data-layer-id')));
    });

    // Convert mm values to mil for bridge server
    var config = {
      nets_to_route: netsToRoute,
      track_width: Math.round((_num('track-width') || 0.3) * MM_TO_MIL * 100) / 100,
      clearance: Math.round((_num('clearance') || 0.25) * MM_TO_MIL * 100) / 100,
      via_size: Math.round((_num('via-size') || 0.5) * MM_TO_MIL * 100) / 100,
      via_drill: Math.round((_num('via-drill') || 0.3) * MM_TO_MIL * 100) / 100,
      grid_step: Math.round((_num('grid-step') || 0.1) * MM_TO_MIL * 100) / 100,
      via_cost: _num('via-cost') || 50,
      max_ripup: _num('max-ripup') || 3,
      layers_to_use: selectedLayers,
      stub_layer_swap: _val('stub-layer-swap'),
      power_nets: _val('power-nets') || '',
      power_widths: _val('power-widths') || '',
      layer_costs: _val('layer-costs') || '',
    };

    routingInProgress = true;
    _id('btn-route').disabled = true;
    _id('btn-cancel').disabled = false;
    setProgress(5);
    setStatus('Routing - ' + netsToRoute.length + ' nets selected to route');
    saveSettings();

    sendToExt('start-routing', config);
  }

  function cancelRouting() {
    sendToExt('cancel-routing', {});
    setStatus('Cancelling...');
  }

  function finishRouting() {
    routingInProgress = false;
    _id('btn-route').disabled = false;
    _id('btn-cancel').disabled = true;
  }

  // ─── UI Helpers ───

  function setProgress(pct) {
    var fill = _id('progress-fill');
    if (fill) fill.style.width = Math.max(0, Math.min(100, pct)) + '%';
  }

  function setStatus(text) {
    var st = _id('progress-text');
    if (st) st.textContent = text;
  }

  // ─── Settings Persistence ───

  function saveSettings() {
    try {
      localStorage.setItem('jlc-eda-design-companion-settings', JSON.stringify({
        selectedNets: Object.keys(selectedNets),
        track_width: _val('track-width'),
        clearance: _val('clearance'),
        via_size: _val('via-size'),
        via_drill: _val('via-drill'),
        grid_step: _val('grid-step'),
        via_cost: _val('via-cost'),
        max_ripup: _val('max-ripup'),
        power_nets: _val('power-nets'),
        power_widths: _val('power-widths'),
        layer_costs: _val('layer-costs'),
      }));
    } catch(e) {}
  }

  function loadSettings() {
    try {
      var raw = localStorage.getItem('jlc-eda-design-companion-settings');
      if (!raw) return;
      var s = JSON.parse(raw);
      if (s.selectedNets) s.selectedNets.forEach(function(n) { selectedNets[n] = true; });
      var fields = ['track_width','clearance','via_size','via_drill','grid_step','via_cost','max_ripup','power_nets','power_widths','layer_costs'];
      fields.forEach(function(key) {
        var elId = key.replace(/_/g, '-');
        if (s[key] !== undefined && s[key] !== null) {
          var el = _id(elId);
          if (el) el.value = s[key];
        }
      });
    } catch(e) {}
  }

  // ─── Start ───
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onLoad);
  } else {
    onLoad();
  }
})();
