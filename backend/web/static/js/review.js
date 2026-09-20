/* Review queue keyboard shortcuts.
   The buttons are real form submits; this only clicks them, so the queue
   behaves identically from the keyboard or the mouse. */
document.addEventListener('keydown', (e) => {
  const stage = document.querySelector('[data-review-stage]');
  if (!stage) return;
  if (e.target.matches('input, textarea, select')) return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;

  const click = (sel) => {
    const btn = stage.querySelector(sel);
    if (btn) {
      e.preventDefault();
      btn.click();
    }
  };

  const key = e.key.toLowerCase();
  if (key === 'c' || e.key === 'ArrowRight') click('[data-review-confirm]');
  if (key === 'r' || e.key === 'ArrowLeft') click('[data-review-reject]');
  if (key === 's') click('[data-review-skip]');
});
