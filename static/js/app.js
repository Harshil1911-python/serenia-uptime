/* ============================================================
   Serenia Uptime — app.js
   Handles: theme toggle, sidebar, manual checks, live refresh
   ============================================================ */

// ---------- Theme ----------
const THEME_KEY = 'serenia-theme';

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem(THEME_KEY, theme);
}

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY) || 'dark';
  applyTheme(saved);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  applyTheme(current === 'dark' ? 'light' : 'dark');
}

// ---------- Sidebar (mobile) ----------
function initSidebar() {
  const hamburger = document.getElementById('hamburger');
  const sidebar    = document.getElementById('sidebar');
  const overlay    = document.getElementById('sidebarOverlay');

  if (!hamburger) return;

  hamburger.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    overlay.classList.toggle('open');
  });

  overlay.addEventListener('click', () => {
    sidebar.classList.remove('open');
    overlay.classList.remove('open');
  });
}

// ---------- Landing nav scroll shadow ----------
function initNavScroll() {
  const nav = document.querySelector('.landing-nav');
  if (!nav) return;
  window.addEventListener('scroll', () => {
    nav.classList.toggle('scrolled', window.scrollY > 20);
  });
}

// ---------- Manual website check ----------
async function manualCheck(siteId, btn) {
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const original  = btn.textContent;

  btn.disabled    = true;
  btn.textContent = 'Checking…';

  try {
    const res  = await fetch(`/api/site/${siteId}/check`, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken, 'Content-Type': 'application/json' },
    });
    const data = await res.json();

    if (data.success) {
      const site    = data.site;
      const card    = btn.closest('.site-card');
      if (!card) { location.reload(); return; }

      // Update status dot
      const dot = card.querySelector('.status-dot');
      if (dot) { dot.className = `status-dot ${site.current_status}`; }

      // Update status badge
      const badge = card.querySelector('.status-badge');
      if (badge) {
        badge.className = `status-badge ${site.current_status}`;
        badge.textContent = site.current_status.toUpperCase();
      }

      // Update metrics
      const metrics = card.querySelectorAll('.metric-value');
      if (metrics[0]) metrics[0].textContent = site.response_time ? Math.round(site.response_time) + ' ms' : '—';
      if (metrics[1]) metrics[1].textContent = site.status_code || '—';
      if (metrics[2]) metrics[2].textContent = site.uptime_percentage + '%';
      if (metrics[3]) metrics[3].textContent = site.last_checked ? formatDate(new Date(site.last_checked)) : 'Just now';

      btn.textContent = '✓ Done';
      setTimeout(() => { btn.textContent = original; btn.disabled = false; }, 1500);
    } else {
      throw new Error(data.error || 'Check failed');
    }
  } catch (err) {
    console.error(err);
    btn.textContent = '✗ Error';
    setTimeout(() => { btn.textContent = original; btn.disabled = false; }, 2000);
  }
}

// ---------- Helper: format date ----------
function formatDate(d) {
  if (!(d instanceof Date) || isNaN(d)) return '—';
  const pad = n => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())} ${d.getDate()} ${d.toLocaleString('en', { month: 'short' })}`;
}

// ---------- Live dashboard refresh (every 60 s) ----------
function initLiveRefresh() {
  if (!document.getElementById('sitesGrid')) return;

  setInterval(async () => {
    try {
      const res  = await fetch('/api/stats');
      const data = await res.json();
      // Update stat values in the card strip (first 4 stat-value elements)
      const vals = document.querySelectorAll('.stat-value');
      if (vals[0]) vals[0].textContent = data.total;
      if (vals[1]) vals[1].textContent = data.online;
      if (vals[2]) vals[2].textContent = data.offline;
      if (vals[3]) vals[3].textContent = (data.avg_response_time || 0) + ' ms';
    } catch (_) { /* network hiccup, ignore */ }
  }, 60_000);
}

// ---------- Flash auto-dismiss ----------
function initFlashDismiss() {
  document.querySelectorAll('.flash').forEach(flash => {
    setTimeout(() => {
      flash.style.opacity = '0';
      flash.style.transition = 'opacity 0.4s';
      setTimeout(() => flash.remove(), 400);
    }, 5000);
  });
}

// ---------- Theme toggle button ----------
function initThemeToggle() {
  const btn = document.getElementById('themeToggle');
  if (btn) btn.addEventListener('click', toggleTheme);
}

// ---------- Boot ----------
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initSidebar();
  initNavScroll();
  initThemeToggle();
  initLiveRefresh();
  initFlashDismiss();
});
