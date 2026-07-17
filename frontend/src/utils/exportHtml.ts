import type { ProductRow } from '../types'
import type { ProductColumn } from './columns'
import { safe } from './formatters'

export function exportCompetitorTableHtml(products: ProductRow[], columns: ProductColumn[]) {
  const payload = {
    columns: columns.map((column) => ({
      key: column.key,
      label: column.label,
      className: column.className || '',
      align: column.align || '',
      sortKey: column.sortKey || '',
      sortType: column.sortType || 'text',
    })),
    rows: products.map((product, index) => ({
      id: String(product.asin || product.title || index),
      search: ['asin', 'title', 'brand', 'seller_name']
        .map((key) => String(product[key] ?? ''))
        .join(' ')
        .toLowerCase(),
      sort: Object.fromEntries(columns.map((column) => [column.key, sortValue(product[column.sortKey || column.key], column.sortType)])),
      cells: Object.fromEntries(
        columns.map((column) => [
          column.key,
          {
            html: column.render(product),
            className: column.className || '',
            align: column.align || '',
          },
        ]),
      ),
    })),
  }
  const dataJson = JSON.stringify(payload).replace(/</g, '\\u003c')
  const html = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>核心竞手表格</title>
<style>
  *{box-sizing:border-box}
  body{margin:0;background:#eef2f6;color:#17202a;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;font-size:13px}
  header{padding:14px 18px;color:#fff;background:#131921;border-bottom:3px solid #ff9900}
  h1{margin:0;font-size:18px}
  .toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:14px 14px 0;padding:12px;background:#fff;border:1px solid #d9e1ea;border-radius:8px}
  .toolbar-left,.toolbar-right,.toolbar-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .toolbar-stack{display:grid;gap:8px;margin:14px 14px 0;padding:12px;background:#fff;border:1px solid #d9e1ea;border-radius:8px}
  .search{width:min(360px,80vw);height:34px;padding:0 11px;border:1px solid #cbd5e1;border-radius:7px;outline:none}
  .search:focus{border-color:#ff9900;box-shadow:0 0 0 3px rgba(255,153,0,.16)}
  .count{color:#667085;font-size:12px}
  .col-toggle{height:30px;padding:0 9px;color:#344054;background:#fff;border:1px solid #d9e1ea;border-radius:7px;font-size:12px;cursor:pointer}
  .col-toggle.active{color:#9a4f00;background:#fff4dc;border-color:#ff9900;font-weight:700}
  .label{color:#667085;font-size:12px;font-weight:800}
  select{height:32px;color:#17202a;background:#fff;border:1px solid #d9e1ea;border-radius:7px}
  .table-wrap{margin:14px;overflow:auto;background:#fff;border:1px solid #d9e1ea;border-radius:8px}
  table{width:100%;min-width:960px;border-collapse:separate;border-spacing:0;table-layout:fixed}
  td{padding:9px 11px;border-bottom:1px solid #edf1f5;text-align:left;vertical-align:top}
  td{width:240px;min-width:220px;max-width:280px}
  td.field-name{position:sticky;left:0;z-index:4;width:132px;min-width:132px;max-width:132px;color:#fff;background:#232f3e;font-weight:800;white-space:nowrap}
  tr.pinned-row td{position:sticky;top:0;z-index:6;background:#fff8ed;box-shadow:0 1px 0 #d9e1ea}
  tr.pinned-row td.field-name{left:0;z-index:8;color:#fff;background:#1b2735}
  .field-cell{display:flex;align-items:center;justify-content:space-between;gap:8px}
  .sort-chip{display:inline-flex;align-items:center;justify-content:center;min-width:26px;height:22px;padding:0 6px;color:#dbeafe;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.22);border-radius:5px;font-size:11px;font-weight:900;cursor:pointer}
  .sort-chip:hover,.sort-chip.active{color:#1b2735;background:#ff9900;border-color:#ff9900}
  a{color:#007185;text-decoration:none;font-weight:700}
  .img-cell img{display:block;width:92px;height:92px;object-fit:contain;background:#fafafa;border:1px solid #eceef1;border-radius:7px}
  .image-link{position:relative;display:inline-block}
  .image-badge{position:absolute;top:6px;left:6px;height:22px;padding:0 7px;color:#9a4f00;background:rgba(255,244,220,.94);border:1px solid #ff9900;border-radius:5px;box-shadow:0 1px 2px rgba(16,24,40,.16);font-size:12px;font-weight:900;line-height:20px}
  .image-badge:before{content:"";position:absolute;inset:-4px;border:2px solid rgba(255,153,0,.78);border-radius:8px;pointer-events:none}
  .title-cell{min-width:220px;max-width:300px}
  .asin-line{color:#5b6470}.asin-line b{color:#1c2230}.parent-line{margin-top:2px;color:#98a2b3;font-size:12px}
  .lbl{color:#98a2b3}.badge-list{display:flex;max-width:140px;flex-wrap:wrap;gap:4px}
  .badge-list span{padding:2px 7px;color:#fff;background:#007185;border-radius:999px;font-size:11px;white-space:nowrap}
  .strike{color:#98a2b3;font-size:11px;text-decoration:line-through}.discount{color:#b42318;font-size:11px;font-weight:800}
  .stars{color:#ffa41c;font-size:15px;white-space:nowrap}.rating-meta,.days-line{margin-top:2px;color:#667085;font-size:12px}
  .cat-path{min-width:180px;max-width:240px;color:#5b6470;line-height:1.55;word-break:break-word}
  .bsr-block{min-width:180px;line-height:1.8}.bsr-row{display:flex;justify-content:space-between;gap:8px}.bsr-row .rk{color:#c0392b;font-weight:800;white-space:nowrap}
  .seller-block,.sales-cell{min-width:150px;line-height:1.7}.seller-block .name{font-weight:700}.seller-block .nat{color:#98a2b3}
  .parent-u{color:#0a7ea4;font-weight:800}.child-u{color:#4a5260}.amount{color:#067647}.sub{color:#067647;font-size:12px}.sub.neg{color:#b42318}
  .trend-cell{width:260px;min-width:220px;max-width:280px}.trend-cell>div{width:100%;min-width:0;max-width:100%}.spark-row{width:100%;min-width:0;max-width:100%;margin-bottom:8px}.spark-label{margin-bottom:2px;color:#667085;font-size:11px;font-weight:800}.spark-sum{margin-left:4px;color:#98a2b3;font-weight:400}
  .spark{position:relative;display:flex;align-items:flex-end;width:100%;min-width:0;max-width:100%;height:54px;gap:4px;padding-top:20px;border-bottom:1px solid #e5e7ea}
  .bar{position:relative;min-width:0;flex:1 1 0;background:linear-gradient(180deg,#ff9900 0%,#ffb84d 100%);border-radius:3px 3px 0 0}.bar.parent{background:linear-gradient(180deg,#37475a 0%,#5a7088 100%)}.bar.zero{background:#e8eaed}
  .bar .val{display:none}
  .bar .tip{display:none}
  #trendTip{position:fixed;left:0;top:0;z-index:9999;max-width:min(220px,calc(100vw - 20px));padding:4px 7px;transform:translate(-50%,-100%);color:#fff;background:#232f3e;border-radius:4px;font-size:10px;line-height:1.3;opacity:0;pointer-events:none;white-space:nowrap;box-shadow:0 6px 18px rgba(16,24,40,.22)}
  .empty{color:#c8ccd2}.hidden{display:none}.table-empty{padding:30px!important;color:#667085;text-align:center!important}
</style>
</head>
<body>
<header>
  <h1>核心竞手表格</h1>
</header>
<div class="toolbar">
  <div class="toolbar-left">
    <input id="search" class="search" type="search" placeholder="搜索标题 / ASIN / 品牌 / 卖家">
    <span id="count" class="count"></span>
  </div>
</div>
<div class="toolbar-stack">
  <div class="toolbar-row"><span class="label">字段</span><div id="fieldToggles" class="toolbar-right"></div></div>
  <div class="toolbar-row"><span class="label">产品</span><div id="productToggles" class="toolbar-right"></div></div>
</div>
<div class="table-wrap">
<table id="table">
  <tbody id="tbody"></tbody>
</table>
</div>
<div id="trendTip"></div>
<script>
const DATA = ${dataJson};
let visibleFields = new Set(DATA.columns.map(c => c.key));
let visibleProducts = new Set(DATA.rows.map(r => r.id));
let query = '';
let sortKey = DATA.columns.find(c => c.key === 'amount')?.key || DATA.columns.find(c => c.sortKey)?.key || '';
let sortDir = 'desc';

const tbody = document.getElementById('tbody');
const count = document.getElementById('count');
const search = document.getElementById('search');
const fieldToggles = document.getElementById('fieldToggles');
const productToggles = document.getElementById('productToggles');
const trendTip = document.getElementById('trendTip');

function cmp(a, b, col) {
  const av = a.sort[col.key];
  const bv = b.sort[col.key];
  if (av == null && bv == null) return 0;
  if (av == null) return 1;
  if (bv == null) return -1;
  if (typeof av === 'number' && typeof bv === 'number') return av - bv;
  return String(av).localeCompare(String(bv), 'zh-Hans-CN');
}

function filteredRows() {
  const rows = (query ? DATA.rows.filter(row => row.search.includes(query)) : DATA.rows.slice())
    .filter(row => visibleProducts.has(row.id));
  const col = DATA.columns.find(c => c.key === sortKey);
  if (!col || !col.sortKey) return rows;
  return rows.sort((a, b) => cmp(a, b, col) * (sortDir === 'asc' ? 1 : -1));
}

function renderControls() {
  fieldToggles.innerHTML = DATA.columns.map(col =>
    '<button type="button" class="col-toggle ' + (visibleFields.has(col.key) ? 'active' : '') + '" data-field="' + col.key + '">' + col.label + '</button>'
  ).join('');
  productToggles.innerHTML = DATA.rows.map(row =>
    '<button type="button" class="col-toggle ' + (visibleProducts.has(row.id) ? 'active' : '') + '" data-product="' + row.id.replace(/"/g, '&quot;') + '">' + row.id + '</button>'
  ).join('');
}

function renderBody(cols, rows) {
  if (!rows.length) {
    tbody.innerHTML = '<tr><td class="table-empty" colspan="2">没有匹配竞手。调整搜索或显示产品。</td></tr>';
    return;
  }
  if (!cols.length) {
    tbody.innerHTML = '<tr><td class="table-empty" colspan="' + (rows.length + 1) + '">没有显示字段。打开至少一个字段。</td></tr>';
    return;
  }
  tbody.innerHTML = cols.map(col => '<tr class="' + (col.key === 'img' ? 'pinned-row' : '') + '">' + fieldCell(col) + rows.map(row => {
    const cell = row.cells[col.key] || { html: '', className: '' };
    const align = cell.align ? ' align-' + cell.align : '';
    return '<td class="' + (cell.className || '') + align + '">' + cell.html + '</td>';
  }).join('') + '</tr>').join('');
}

function fieldCell(col) {
  const button = col.sortKey
    ? '<button type="button" class="sort-chip ' + (sortKey === col.key ? 'active' : '') + '" data-sort="' + col.key + '" title="按' + col.label + '排序">' + (sortKey === col.key ? (sortDir === 'asc' ? '▲' : '▼') : '↕') + '</button>'
    : '';
  return '<td class="field-name"><div class="field-cell"><span>' + col.label + '</span>' + button + '</div></td>';
}

function render() {
  const cols = DATA.columns.filter(col => visibleFields.has(col.key));
  const rows = filteredRows();
  count.textContent = rows.length + ' / ' + DATA.rows.length + ' 个竞手';
  renderControls();
  renderBody(cols, rows);
}

search.addEventListener('input', event => {
  query = event.target.value.trim().toLowerCase();
  render();
});

fieldToggles.addEventListener('click', event => {
  const button = event.target.closest('button[data-field]');
  if (!button) return;
  const key = button.dataset.field;
  if (visibleFields.has(key)) visibleFields.delete(key); else visibleFields.add(key);
  render();
});

productToggles.addEventListener('click', event => {
  const button = event.target.closest('button[data-product]');
  if (!button) return;
  const key = button.dataset.product;
  if (visibleProducts.has(key)) visibleProducts.delete(key); else visibleProducts.add(key);
  render();
});

tbody.addEventListener('click', event => {
  const button = event.target.closest('button[data-sort]');
  if (!button) return;
  const key = button.dataset.sort;
  if (sortKey === key) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
  else {
    sortKey = key;
    const col = DATA.columns.find(c => c.key === key);
    sortDir = col && (col.sortType === 'text' || col.sortType === 'date') ? 'asc' : 'desc';
  }
  render();
});

tbody.addEventListener('mousemove', event => {
  const bar = event.target.closest('.bar');
  if (!bar) {
    trendTip.style.opacity = '0';
    return;
  }
  const tip = bar.querySelector('.tip');
  if (!tip) return;
  trendTip.textContent = tip.textContent;
  trendTip.style.opacity = '1';
  const margin = 10;
  const rect = trendTip.getBoundingClientRect();
  const left = Math.min(Math.max(event.clientX, margin + rect.width / 2), window.innerWidth - margin - rect.width / 2);
  const top = Math.max(event.clientY - 10, margin + rect.height);
  trendTip.style.left = left + 'px';
  trendTip.style.top = top + 'px';
});

tbody.addEventListener('mouseleave', () => {
  trendTip.style.opacity = '0';
});

render();
</script>
</body>
</html>`
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const timestamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')
  link.href = url
  link.download = `competitor-table-${timestamp}.html`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function sortValue(value: unknown, type: ProductColumn['sortType']): string | number | null {
  if (value == null || value === '') return null
  if (type === 'number') {
    const number = Number(String(value).replaceAll(',', ''))
    return Number.isFinite(number) ? number : null
  }
  if (type === 'date') {
    const time = Date.parse(String(value))
    return Number.isFinite(time) ? time : null
  }
  return String(value).toLowerCase()
}
