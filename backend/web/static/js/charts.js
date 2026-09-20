/* Chart.js wiring. Every chart reads its data from a json_script block, so
   no chart ever fetches anything. */
import { jsonData } from './core.js';

const css = (name) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function baseOptions() {
  const grid = 'rgba(255,255,255,.06)';
  const tick = css('--text-faint') || '#6c7280';
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        display: false,
        labels: { color: tick, font: { family: 'Inter', size: 11 }, usePointStyle: true },
      },
      tooltip: {
        backgroundColor: 'rgba(8,8,12,.94)',
        borderColor: 'rgba(255,255,255,.12)',
        borderWidth: 1,
        padding: 10,
        cornerRadius: 10,
        displayColors: false,
      },
    },
    scales: {
      x: {
        grid: { color: grid, drawBorder: false },
        ticks: { color: tick, font: { size: 10 }, maxRotation: 0, autoSkipPadding: 16 },
      },
      y: {
        grid: { color: grid, drawBorder: false },
        ticks: { color: tick, font: { size: 10 }, precision: 0 },
        beginAtZero: true,
      },
    },
  };
}

function gradient(ctx, area, from, to) {
  if (!area) return from;
  const g = ctx.createLinearGradient(0, area.top, 0, area.bottom);
  g.addColorStop(0, from);
  g.addColorStop(1, to);
  return g;
}

function lineChart(canvas, data) {
  return new Chart(canvas, {
    type: 'line',
    data: {
      labels: data.labels,
      datasets: [
        {
          data: data.values,
          borderColor: css('--accent') || '#5b8cff',
          borderWidth: 2,
          tension: 0.36,
          pointRadius: 0,
          pointHoverRadius: 4,
          fill: true,
          backgroundColor: (c) =>
            gradient(c.chart.ctx, c.chart.chartArea, 'rgba(91,140,255,.32)', 'rgba(91,140,255,0)'),
        },
      ],
    },
    options: baseOptions(),
  });
}

function donutChart(canvas, data, colors) {
  const opts = baseOptions();
  delete opts.scales;
  opts.cutout = '68%';
  opts.plugins.legend.display = true;
  opts.plugins.legend.position = 'bottom';
  opts.plugins.tooltip.displayColors = true;
  return new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: data.labels,
      datasets: [
        {
          data: data.values,
          backgroundColor: colors,
          borderColor: 'rgba(0,0,0,.5)',
          borderWidth: 2,
        },
      ],
    },
    options: opts,
  });
}

function barChart(canvas, data, horizontal) {
  const opts = baseOptions();
  if (horizontal) opts.indexAxis = 'y';
  return new Chart(canvas, {
    type: 'bar',
    data: {
      labels: data.labels,
      datasets: [
        {
          data: data.values,
          backgroundColor: 'rgba(91,140,255,.55)',
          hoverBackgroundColor: 'rgba(91,140,255,.85)',
          borderRadius: 6,
          borderSkipped: false,
          maxBarThickness: 34,
        },
      ],
    },
    options: opts,
  });
}

const SEV_COLORS = ['#35d0a5', '#f5b83d', '#ff5a6e'];
const MIX_COLORS = ['#5b8cff', '#9d6bff', '#35d0a5', '#f5b83d', '#ff5a6e', '#6c7280', '#3ad1c8'];

document.addEventListener('DOMContentLoaded', () => {
  if (typeof Chart === 'undefined') return;
  Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
  Chart.defaults.color = css('--text-faint') || '#6c7280';

  document.querySelectorAll('[data-chart]').forEach((canvas) => {
    const data = jsonData(canvas.dataset.chartData);
    if (!data || !data.labels) return;
    const kind = canvas.dataset.chart;
    if (kind === 'line') {
      lineChart(canvas, data);
    } else if (kind === 'donut') {
      donutChart(canvas, data, canvas.dataset.chartPalette === 'severity' ? SEV_COLORS : MIX_COLORS);
    } else if (kind === 'bar') {
      barChart(canvas, data, canvas.dataset.chartHorizontal === 'true');
    }
  });
});
