(function() {
  function escHtml(str) { if (!str) return ''; return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  function loadSummary() {
    fetch('/api/stats').then(function(r) { return r.json(); }).then(function(stats) {
      document.getElementById('stat-solved').textContent = stats.solved;
      document.getElementById('stat-total').textContent = stats.total;
      var pct = stats.total > 0 ? (stats.solved / stats.total * 100).toFixed(0) + '%' : '0%';
      document.getElementById('stat-progress').textContent = pct;
      var body = document.getElementById('recent-solutions');
      if (stats.recent_solutions && stats.recent_solutions.length > 0) {
        body.innerHTML = stats.recent_solutions.map(function(s) {
          var slug = s.slug || '';
          return '<tr style="border-bottom: 1px solid var(--border);">' +
            '<td class="pl-3"><a href="/problem/' + slug + '/" style="color: var(--text-primary);">' + slug.replace('/', '') + ' &mdash; ' + escHtml(s.title) + '</a></td>' +
            '<td><span class="verdict-accepted"><i class="fas fa-check-circle mr-1"></i>Accepted</span></td>' +
            '<td><a href="/problem/' + slug + '/" class="btn-outline-accent btn-sm" style="padding: 0.2rem 0.6rem; font-size: 0.78rem;">View</a></td></tr>';
        }).join('');
      } else {
        body.innerHTML = '<tr><td colspan="3" class="text-center text-secondary py-3">No solutions yet.</td></tr>';
      }
    }).catch(function() {
      document.getElementById('stat-solved').textContent = '?';
      document.getElementById('stat-total').textContent = '?';
      document.getElementById('stat-progress').textContent = '?';
    });
  }

  if (document.getElementById('stat-solved')) loadSummary();
})();
