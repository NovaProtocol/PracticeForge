(function() {
  var KEY = 'solvespace-theme';
  var current = localStorage.getItem(KEY) || 'dark';
  applyTheme(current);

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(KEY, theme);
    var btn = document.getElementById('theme-toggle');
    if (btn) {
      btn.innerHTML = theme === 'dark'
        ? '<i class="fas fa-sun"></i>'
        : '<i class="fas fa-moon"></i>';
      btn.title = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
    }
  }

  function toggleTheme() {
    var next = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    applyTheme(next);
  }

  document.addEventListener('DOMContentLoaded', function() {
    var btn = document.getElementById('theme-toggle');
    if (btn) btn.addEventListener('click', toggleTheme);
  });
})();
