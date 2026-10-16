const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
document.querySelectorAll('form[data-confirm]').forEach(f =>
  f.addEventListener('submit', e => { if (!confirm(f.dataset.confirm)) e.preventDefault(); }));
document.querySelectorAll('.toast').forEach(t => setTimeout(() => t.classList.add('gone'), 5000));
// stagger rows, tiles and loan cards
document.querySelectorAll('tbody').forEach(tb => [...tb.rows].slice(0, 14).forEach((r, i) => r.style.setProperty('--n', i)));
document.querySelectorAll('.tile').forEach((t, i) => t.style.setProperty('--n', Math.min(i, 16)));
// count-up numbers
if (!calm) document.querySelectorAll('[data-count]').forEach(el => {
  const to = parseInt(el.textContent.replace(/\D/g, ''), 10) || 0;
  if (!to) return;
  const t0 = performance.now(), dur = 1000;
  const step = t => { const p = Math.min((t - t0) / dur, 1);
    el.textContent = Math.round(to * (1 - Math.pow(1 - p, 3)));
    if (p < 1) requestAnimationFrame(step); };
  el.textContent = '0'; requestAnimationFrame(step);
});
// button ripple
document.addEventListener('click', e => {
  const b = e.target.closest('.btn'); if (!b || calm) return;
  const r = b.getBoundingClientRect(), s = document.createElement('span');
  s.className = 'ripple'; const d = Math.max(r.width, r.height);
  s.style.cssText = `width:${d}px;height:${d}px;left:${e.clientX - r.left - d / 2}px;top:${e.clientY - r.top - d / 2}px`;
  b.appendChild(s); setTimeout(() => s.remove(), 600);
});
