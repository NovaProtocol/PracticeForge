(function() {
  var P = window.__solution || {};

  document.querySelector('.results-table')?.addEventListener('click', function(e) {
    var btn = e.target.closest('.output-btn');
    if (!btn) return;
    var tr = btn.closest('tr');
    var or = tr && tr.nextElementSibling;
    if (or && or.classList.contains('output-row')) {
      or.style.display = or.style.display === 'none' ? '' : 'none';
      btn.textContent = or.style.display === 'none' ? 'Output' : 'Close';
    }
  });

  var rerunBtn = document.getElementById('rerun-btn');
  if (rerunBtn) rerunBtn.addEventListener('click', async function() {
    var btn = this; var status = document.getElementById('rerun-status');
    btn.disabled = true; status.textContent = 'Queuing...';
    try {
      var r = await fetch('/api/re-run/' + P.solutionId, { method: 'POST' });
      var d = await r.json();
      status.textContent = 'Queued (#' + d.queue_id + '). Reload to see results.';
      setTimeout(function() { btn.disabled = false; }, 3000);
    } catch(e) { status.textContent = 'Error: ' + e.message; btn.disabled = false; }
  });
})();
