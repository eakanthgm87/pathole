/* Reports table: checkbox selection driving the bulk action bar. */
document.addEventListener('DOMContentLoaded', () => {
  const table = document.querySelector('[data-bulk-table]');
  const bar = document.querySelector('[data-bulk-bar]');
  if (!table || !bar) return;

  const idsField = bar.querySelector('[name=report_ids]');
  const countEl = bar.querySelector('[data-bulk-count]');
  const all = table.querySelector('[data-check-all]');
  const boxes = () => Array.from(table.querySelectorAll('[data-check]'));

  const sync = () => {
    const chosen = boxes().filter((b) => b.checked).map((b) => b.value);
    if (idsField) idsField.value = chosen.join(',');
    if (countEl) countEl.textContent = chosen.length;
    bar.classList.toggle('show', chosen.length > 0);
    if (all) {
      all.checked = chosen.length > 0 && chosen.length === boxes().length;
      all.indeterminate = chosen.length > 0 && chosen.length < boxes().length;
    }
  };

  table.addEventListener('change', (e) => {
    if (e.target.matches('[data-check-all]')) {
      boxes().forEach((b) => {
        b.checked = e.target.checked;
      });
    }
    if (e.target.matches('[data-check], [data-check-all]')) sync();
  });

  sync();
});
