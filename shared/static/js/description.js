(function() {
  var P = window.__problem || {};

  function copyText(btn) {
    var text = btn.dataset.text;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function() {
          btn.textContent = 'Copied!'; btn.classList.add('copied');
          setTimeout(function() { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 1000);
        }).catch(function() { fallbackCopy(text, btn); });
      } else { fallbackCopy(text, btn); }
    } catch(e) { fallbackCopy(text, btn); }
  }
  function fallbackCopy(text, btn) {
    var ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); btn.textContent = 'Copied!'; } catch(e) {}
    document.body.removeChild(ta);
    setTimeout(function() { if (btn) btn.textContent = 'Copy'; }, 1000);
  }

  document.querySelectorAll('.copy-btn').forEach(function(btn) {
    btn.addEventListener('click', function() { copyText(btn); });
  });

  document.querySelectorAll('.section-header').forEach(function(hdr) {
    hdr.addEventListener('click', function() {
      var id = hdr.dataset.section;
      var el = document.getElementById(id);
      if (!el) return;
      el.classList.toggle('collapsed');
      hdr.classList.toggle('open');
    });
  });

  window.descriptionApi = window.descriptionApi || {};
  window.descriptionApi.reloadSubmissions = function() {
    var el = document.getElementById('desc-submissions');
    if (!el || el.style.display === 'none') return;
    fetch('/api/submissions/' + P.problemId).then(function(r) { return r.json(); }).then(function(subs) {
      el.innerHTML = subs.map(function(s) {
        var vc = s.verdict === 'Accepted' ? 'verdict-accepted' : 'verdict-wrong';
        return '<div class="submission-item"><span class="' + vc + '">' + s.verdict + '</span>' +
          '<span class="text-secondary"> \u2014 ' + s.passed_count + '/' + s.total_count + '</span>' +
          (s.timing_ms ? '<span class="text-secondary"> \u00b7 ' + s.timing_ms + 'ms</span>' : '') +
          (s.memory_kb ? '<span class="text-secondary"> \u00b7 ' + (s.memory_kb > 1024 ? (s.memory_kb/1024).toFixed(1) + 'MB' : s.memory_kb.toLocaleString() + 'KB') + '</span>' : '') +
          '<span class="text-secondary" style="float:right;font-size:0.78rem;">' + (s.created_at || '') + '</span>' +
          '<a href="/problem/' + P.contestId + '/' + P.index + '/solution/' + s.id + '" class="btn-outline-accent btn-sm" style="padding:0.15rem 0.6rem;font-size:0.72rem;text-decoration:none;">View solution</a></div>';
      }).join('') || '<p class="text-secondary" style="font-size:0.85rem;padding:1rem 1.25rem;">No submissions yet.</p>';
    }).catch(function() {});
  };
  document.querySelectorAll('.desc-tab').forEach(function(tab) {
    tab.addEventListener('click', function() {
      document.querySelectorAll('.desc-tab').forEach(function(t) { t.classList.remove('active'); });
      tab.classList.add('active');
      document.getElementById('desc-content').style.display = tab.dataset.tab === 'description' ? 'block' : 'none';
      document.getElementById('desc-submissions').style.display = tab.dataset.tab === 'submissions' ? 'block' : 'none';
      if (tab.dataset.tab === 'submissions') window.descriptionApi.reloadSubmissions();
    });
  });

  var solBtn = document.getElementById('get-solution-btn');
  if (solBtn) solBtn.addEventListener('click', function() {
    document.getElementById('confirm-modal-title').textContent = 'View Solution';
    document.getElementById('confirm-modal-text').textContent = 'Are you sure? This is an intentional action to reveal the solution.';
    document.getElementById('confirm-modal-yes').addEventListener('click', function h() {
      document.getElementById('confirm-modal-yes').removeEventListener('click', h);
      jQuery('#confirm-modal').modal('hide');
      var pre = document.getElementById('solution-code');
      if (pre) {
        pre.style.display = pre.style.display === 'none' ? 'block' : 'none';
        document.getElementById('get-solution-btn').textContent = pre.style.display === 'none' ? 'Get solution' : 'Hide solution';
      }
    });
    jQuery('#confirm-modal').modal('show');
  });

  function _inlineLen(val) {
    var s = JSON.stringify(val);
    if (s.length > 80) return null;
    return s;
  }

  function _toYaml(val, indent) {
    indent = indent || 0;
    var pad = '  '.repeat(indent);
    if (val === null || val === undefined) return 'null';
    if (typeof val === 'string') {
      if (val.includes('\n') || val.includes(': ') || val === '') return JSON.stringify(val);
      return val;
    }
    if (typeof val === 'number' || typeof val === 'boolean') return String(val);
    if (Array.isArray(val)) {
      if (val.length === 0) return '[]';
      var inline = _inlineLen(val);
      if (inline) return inline;
      return val.map(function(v) {
        if (typeof v === 'object' && v !== null) {
          var lines = _toYaml(v, indent + 1).split('\n');
          return pad + '  - ' + lines[0] + '\n' + lines.slice(1).map(function(l) { return pad + '    ' + l; }).join('\n');
        }
        return pad + '  - ' + _toYaml(v);
      }).join('\n');
    }
    if (typeof val === 'object') {
      var keys = Object.keys(val);
      if (keys.length === 0) return '{}';
      return keys.map(function(k) {
        var v = val[k];
        if (typeof v === 'object' && v !== null) {
          var inline = _inlineLen(v);
          if (inline) return pad + k + ': ' + inline;
          return pad + k + ':\n' + _toYaml(v, indent + 1);
        }
        return pad + k + ': ' + _toYaml(v);
      }).join('\n');
    }
    return String(val);
  }

  document.querySelectorAll('.sample-kwargs, .sample-output').forEach(function(pre) {
    try { var val = JSON.parse(pre.textContent); pre.textContent = _toYaml(val); } catch(e) {}
  });
})();
