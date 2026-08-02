(function() {
  var P = window.__problem || {};
  var C = { contestId: P.contestId, index: P.index, problemId: P.problemId };
  var el = function(id) { return document.getElementById(id); };
  var editorEl = el('editor-wrapper');
  var tabsEl = el('file-tabs');
  var baseCode = P.baseCode || "class Solution:\n    def run(self, input: str) -> str:\n        ";

  function showConfirm(title, text, cb) {
    document.getElementById('confirm-modal-title').textContent = title;
    document.getElementById('confirm-modal-text').textContent = text;
    var btn = document.getElementById('confirm-modal-yes');
    var handler = function() { btn.removeEventListener('click', handler); jQuery('#confirm-modal').modal('hide'); cb(); };
    btn.addEventListener('click', handler);
    jQuery('#confirm-modal').modal('show');
  }

  function showNewFileModal() {
    var input = document.getElementById('newfile-input');
    input.value = '';
    var btn = document.getElementById('newfile-create-btn');
    var handler = function() {
      btn.removeEventListener('click', handler);
      var name = input.value.trim();
      if (!name) return;
      if (files.some(function(f) { return f.filename === name; })) {
        input.style.borderColor = '#f87171';
        input.setAttribute('placeholder', 'Already exists');
        setTimeout(function() { input.style.borderColor = ''; input.setAttribute('placeholder', 'e.g. approach-b'); }, 1500);
        input.focus();
        input.select();
        return;
      }
      jQuery('#newfile-modal').modal('hide');
      fetch('/api/files/' + C.problemId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: name, code: '' })
      }).then(function(r) { return r.json(); }).then(function() {
        files.push({ filename: name, code: '', last_ran: null });
        switchFile(name);
      });
    };
    btn.addEventListener('click', handler);
    input.addEventListener('keydown', function(e) { if (e.key === 'Enter') btn.click(); });
    jQuery('#newfile-modal').modal('show');
    setTimeout(function() { input.focus(); }, 300);
  }

  var files = [];
  var activeFile = null;
  var saveTimer;

  function initEditor(code) {
    if (window.editor) { window.editor.setValue(code || ''); window.editor.focus(); return; }
    var textarea = document.createElement('textarea');
    textarea.id = 'code'; textarea.style.display = 'none';
    textarea.textContent = code || '';
    editorEl.appendChild(textarea);
    window.editor = CodeMirror.fromTextArea(textarea, {
      lineNumbers: true, autoCloseBrackets: true, matchBrackets: true,
      tabSize: 4, indentUnit: 4, mode: 'python', theme: 'material-darker',
      indentWithTabs: false, electricChars: true, smartIndent: true,
      styleActiveLine: true, showTrailingSpace: true,
      foldGutter: true,
      gutters: ["CodeMirror-foldgutter", "CodeMirror-linenumbers"],
      highlightSelectionMatches: true,
      scrollbarStyle: 'overlay',
      rulers: [{column: 79, color: '#2a2a3e'}],
      keyMap: 'sublime',
      extraKeys: {
        'Ctrl-Enter': function() { el('run-btn').click(); },
        'Cmd-Enter': function() { el('run-btn').click(); },
        'Ctrl-D': function(cm) { cm.execCommand('deleteLine'); },
        'Cmd-D': function(cm) { cm.execCommand('deleteLine'); },
        'Ctrl-S': function() { saveCurrentFile(); },
        'Cmd-S': function() { saveCurrentFile(); },
        'Ctrl-Space': function(cm) { cm.showHint({hint: CodeMirror.hint.anyword}); }
      }
    });
    window.editor.on('change', function() {
      isDirty = true;
    });

    setInterval(function() {
      if (isDirty && activeFile && window.editor) {
        isDirty = false;
        var code = window.editor.getValue();
        var fd = new URLSearchParams({ code: code, filename: activeFile });
        navigator.sendBeacon('/api/save/' + C.contestId + '/' + C.index, fd);
      }
    }, 1000);
  }

  function saveCurrentFile() {
    if (!activeFile || !window.editor) return;
    var code = window.editor.getValue();
    var fd = new URLSearchParams({ code: code, filename: activeFile });
    navigator.sendBeacon('/api/save/' + C.contestId + '/' + C.index, fd);
    isDirty = false;
  }

  function renderTabs() {
    tabsEl.innerHTML = '';
    files.forEach(function(f) {
      var tab = document.createElement('div');
      tab.className = 'file-tab' + (f.filename === activeFile ? ' active' : '');
      tab.dataset.filename = f.filename;
      tab.innerHTML = escHtml(f.filename) + '<button class="tab-close" data-filename="' + escHtml(f.filename) + '">&times;</button>';
      tab.addEventListener('click', function(e) {
        if (e.target.closest('.tab-close')) return;
        switchFile(f.filename);
      });
      tabsEl.appendChild(tab);
    });
    var addBtn = document.createElement('button');
    addBtn.className = 'file-tab-add';
    addBtn.textContent = '+';
    addBtn.title = 'New file';
    addBtn.addEventListener('click', showNewFileModal);
    tabsEl.appendChild(addBtn);
    tabsEl.querySelectorAll('.tab-close').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var name = btn.dataset.filename;
        if (files.length <= 1) return;
        showConfirm('Delete file', 'Delete "' + name + '"?', function() {
          files = files.filter(function(f) { return f.filename !== name; });
          if (activeFile === name) {
            activeFile = files[0] ? files[0].filename : 'main.py';
            switchFile(activeFile);
          }
          renderTabs();
          fetch('/api/files/' + C.problemId + '/' + encodeURIComponent(name), { method: 'DELETE' });
        });
      });
    });
  }

  function switchFile(filename) {
    if (activeFile && window.editor) saveCurrentFile();
    activeFile = filename;
    fetch('/api/auto-save/' + C.problemId + '?filename=' + encodeURIComponent(filename)).then(function(r) { return r.json(); }).then(function(d) {
      var code = d.code || '';
      if (filename === 'main.py' && !code) code = baseCode;
      initEditor(code);
      renderTabs();
    });
  }

  function escHtml(str) { if (!str) return ''; return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  var fontSize = 14;
  var isDirty = false;

  function applyFontSize() { var cm = editorEl.querySelector('.CodeMirror'); if (cm) { cm.style.fontSize = fontSize + 'px'; if (window.editor) window.editor.refresh(); } }
  el('font-inc').addEventListener('click', function() { fontSize = Math.min(32, fontSize + 2); applyFontSize(); });
  el('font-dec').addEventListener('click', function() { fontSize = Math.max(8, fontSize - 2); applyFontSize(); });
  el('reset-btn').addEventListener('click', function() { showConfirm('Reset code', 'Reset to original template?', function() { window.editor.setValue(baseCode); window.editor.focus(); }); });
  el('lastran-btn').addEventListener('click', function() {
    fetch('/api/auto-save/' + C.problemId + '?filename=' + encodeURIComponent(activeFile || 'main.py')).then(function(r) { return r.json(); }).then(function(d) {
      if (d.last_ran) { window.editor.setValue(d.last_ran); window.editor.focus(); }
      else { alert('No previously run code saved.'); }
    }).catch(function() {});
  });
  var fsActive = false;
  el('fullscreen-btn').addEventListener('click', function() {
    fsActive = !fsActive;
    document.body.classList.toggle('editor-fullscreen', fsActive);
    if (fsActive && editorEl.requestFullscreen) editorEl.requestFullscreen();
    else if (!fsActive && document.exitFullscreen) document.exitFullscreen();
    setTimeout(function() { if (window.editor) window.editor.refresh(); }, 150);
  });
  document.addEventListener('fullscreenchange', function() {
    if (!document.fullscreenElement) { fsActive = false; document.body.classList.remove('editor-fullscreen'); if (window.editor) window.editor.refresh(); }
  });
  el('run-btn').addEventListener('click', function() {
    jQuery('#solver-modal').modal('show');
    jQuery('#solver-modal').data('action', 'run');
    el('modal-tab-testcases').click();
  });
  var sidebarToggle = el('sidebar-toggle');
  if (sidebarToggle) sidebarToggle.addEventListener('click', function() {
    var p = document.getElementById('description-panel');
    var w = document.getElementById('workspace-panel');
    p.classList.toggle('collapsed');
    if (p.classList.contains('collapsed')) { w.classList.remove('col-lg-7'); w.classList.add('col-lg-12'); }
    else { w.classList.remove('col-lg-12'); w.classList.add('col-lg-7'); }
    localStorage.setItem('solvespace-sidebar', p.classList.contains('collapsed') ? 'collapsed' : 'open');
  });
  el('format-btn').addEventListener('click', function() {
    var btn = el('format-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    fetch('/api/format', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ code: window.editor.getValue() })
    }).then(function(r) { return r.json(); }).then(function(d) {
      if (d.formatted) { window.editor.setValue(d.formatted); window.editor.focus(); }
      else if (d.error) { alert('Format error: ' + d.error); }
    }).catch(function(e) { alert('Format failed: ' + e.message); }).finally(function() {
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i>';
    });
  });

  fetch('/api/files/' + C.problemId).then(function(r) { return r.json(); }).then(function(data) {
    if (data.length === 0) {
      fetch('/api/files/' + C.problemId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: 'main.py', code: baseCode })
      }).then(function(r) { return r.json(); }).then(function() {
        files = [{ filename: 'main.py', code: baseCode, last_ran: null }];
        switchFile('main.py');
      });
    } else {
      files = data;
      switchFile(activeFile || 'main.py');
    }
  });
})();
