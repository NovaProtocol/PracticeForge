(function() {
  function escHtml(str) { if (!str) return ''; return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  function applyFilters() {
    var comps = Array.from(document.querySelectorAll('.filter-completion:checked')).map(function(c) { return c.value; });
    var topics = Array.from(document.querySelectorAll('.filter-topic:checked')).map(function(c) { return c.value; });
    var dMin = parseInt(document.getElementById('diff-min')?.value) || 0;
    var dMax = parseInt(document.getElementById('diff-max')?.value) || 9999;
    document.querySelectorAll('.problem-card').forEach(function(card) {
      var completion = card.dataset.completion;
      var cardTags = [];
      try { cardTags = JSON.parse(card.dataset.tags); } catch(e) {}
      var diff = parseInt(card.dataset.difficulty) || 0;
      card.style.display = (comps.length===0||comps.includes(completion)) && (topics.length===0||cardTags.some(function(t) { return topics.includes(t); })) && diff>=dMin && diff<=dMax ? '' : 'none';
    });
  }

  function setView(mode) {
    var list = document.getElementById('problem-list');
    var cards = document.getElementById('view-cards');
    var listBtn = document.getElementById('view-list');
    if (!list) return;
    if (mode === 'list') {
      list.classList.remove('row');
      list.querySelectorAll('.problem-card').forEach(function(c) { c.classList.remove('col-md-6','col-xl-4','mb-4'); });
      cards?.classList.remove('active');
      listBtn?.classList.add('active');
    } else {
      list.classList.add('row');
      list.querySelectorAll('.problem-card').forEach(function(c) { c.classList.add('col-md-6','col-xl-4','mb-4'); });
      cards?.classList.add('active');
      listBtn?.classList.remove('active');
    }
    try { localStorage.setItem('problemView', mode); } catch(e) {}
  }

  function cardHtml(p) {
    var diffCls = p.difficulty_rating < 1200 ? 'easy' : p.difficulty_rating < 1600 ? 'medium' : 'hard';
    var diffBadge = p.difficulty_rating ? '<span class="badge-difficulty badge-' + diffCls + '" style="line-height:1.4;">' + p.difficulty_rating + '</span>' : '';
    var compBadge = '';
    if (p.completion === 'completed') compBadge = '<span class="badge-difficulty badge-easy" style="font-size:0.7rem;">Completed</span>';
    else if (p.completion === 'in_progress') compBadge = '<span class="badge-difficulty badge-medium" style="font-size:0.7rem;">In Progress</span>';
    else compBadge = '<span class="badge-difficulty" style="background:rgba(136,136,160,0.15);color:var(--text-secondary);font-size:0.7rem;">Incomplete</span>';
    var slug = p.contest_id + '/' + p.problem_index;
    return '<div class="col-md-6 col-xl-4 mb-4 problem-card" data-completion="' + p.completion + '" data-tags=\'' + JSON.stringify(p.tags) + '\' data-difficulty="' + (p.difficulty_rating||0) + '">' +
      '<a href="/problem/' + slug + '/" class="card-link">' +
      '<div class="card p-3 h-100"><div class="d-flex justify-content-between align-items-center mb-2">' +
      '<span class="tag" style="margin-bottom:0;">' + slug + '</span>' + diffBadge + '</div>' +
      '<h5 style="font-weight:600;font-size:1rem;">' + escHtml(p.title) + '</h5>' +
      '<div>' + compBadge + '</div></div></a></div>';
  }

  // API-loaded lists (private index): fetch and render.
  function loadProblems() {
    Promise.all([
      fetch('/api/problems').then(function(r) { return r.json(); }),
      fetch('/api/tags').then(function(r) { return r.json(); }),
    ]).then(function(res) {
      var problems = res[0], tags = res[1];
      var tf = document.getElementById('topic-filters');
      if (tf) tf.innerHTML = tags.map(function(t) {
        return '<label class="d-block" style="font-size:0.85rem;cursor:pointer;"><input type="checkbox" class="filter-topic" value="' + escHtml(t) + '" checked> ' + escHtml(t) + '</label>';
      }).join('');
      var pl = document.getElementById('problem-list');
      if (pl) pl.innerHTML = problems.map(cardHtml).join('');
      applyFilters();
      try { setView(localStorage.getItem('problemView') || 'cards'); } catch(e) {}
    }).catch(function(e) {
      console.error('loadProblems failed:', e);
      var pl = document.getElementById('problem-list');
      if (pl) pl.innerHTML = '<div class="loading" style="width:100%;color:#f87171;">Error: ' + e.message + '</div>';
    });
  }

  document.querySelectorAll('.filter-completion, .filter-topic').forEach(function(el) { el.addEventListener('change', applyFilters); });
  ['diff-min','diff-max'].forEach(function(id) { document.getElementById(id)?.addEventListener('input', applyFilters); });
  document.getElementById('clear-filters')?.addEventListener('click', function() {
    document.querySelectorAll('.filter-completion').forEach(function(c) { c.checked = false; });
    document.querySelectorAll('.filter-topic').forEach(function(c) { c.checked = true; });
    document.getElementById('diff-min').value = '';
    document.getElementById('diff-max').value = '';
    applyFilters();
  });
  document.getElementById('view-cards')?.addEventListener('click', function() { setView('cards'); });
  document.getElementById('view-list')?.addEventListener('click', function() { setView('list'); });

  window.solveSpaceProblems = { applyFilters: applyFilters, setView: setView, cardHtml: cardHtml };

  // Auto-load only if the list is empty or shows a loading placeholder
  // (API-driven page). Server-rendered pages already have cards.
  var pl = document.getElementById('problem-list');
  if (pl && !pl.querySelector('.problem-card')) loadProblems();
})();
