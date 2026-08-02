(function() {
  document.querySelectorAll('.re-run-btn').forEach(function(btn) {
    btn.addEventListener('click', async function() {
      var id = btn.dataset.id;
      btn.disabled = true; btn.textContent = 'Queuing...';
      try {
        var r = await fetch('/api/re-run/' + id, { method: 'POST' });
        await r.json();
        btn.textContent = 'Re-run queued';
      } catch(e) { btn.textContent = 'Error'; btn.disabled = false; }
    });
  });
})();
