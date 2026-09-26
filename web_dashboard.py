#!/usr/bin/env python3
"""
entropy-arb 網頁監控儀表板
用法：python3 web_dashboard.py
瀏覽器開啟：http://localhost:8765
"""
import csv, json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime

BASE        = os.path.dirname(os.path.abspath(__file__))
MINUTES_CSV = os.path.join(BASE, "logs", "minutes.csv")
TRADES_CSV  = os.path.join(BASE, "logs", "trades.csv")
ENGINE_LOG  = os.path.join(BASE, "logs", "engine.log")
PORT        = 8765

# 與 config.yaml 一致的門檻設定
MIDLINE_BPS   = 55    # 中樞（由 tools/analyze.py 建議）
UPPER_BPS     = 15    # config upper_bps
LOWER_BPS     = 15    # config lower_bps
# 實際引擎觸發閾值（book.py 的計算）：
#   賣 Entropy：sell_edge = (entropy_bid/lighter_ask - 1)*10000 >= SELL_TRIGGER
#   買 Entropy：buy_edge  = (lighter_bid/entropy_ask - 1)*10000 >= BUY_TRIGGER
SELL_TRIGGER  = MIDLINE_BPS + UPPER_BPS    # 70 bps
BUY_TRIGGER   = LOWER_BPS  - MIDLINE_BPS  # -40 bps


def _csv_tail(path, n=100):
    if not os.path.exists(path):
        return []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))[-n:]
    except Exception:
        return []


def _log_tail(path, n=20):
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return [l.rstrip() for l in f.readlines()[-n:]]
    except Exception:
        return []


HTML = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ANTH 套利監控</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0d0b18;--card:#161225;--card2:#1e1a2e;
  --purple:#a78bfa;--pink:#f472b6;--green:#34d399;
  --red:#f87171;--yellow:#fbbf24;--blue:#60a5fa;
  --text:#e2e0f0;--muted:#5e5a78;--border:#252038;
}}
body{{font-family:'Inter',system-ui,sans-serif;background:var(--bg);
  color:var(--text);min-height:100vh;padding:20px 24px;
  background-image:
    radial-gradient(ellipse at 15% 5%, rgba(167,139,250,.07) 0%,transparent 55%),
    radial-gradient(ellipse at 85% 85%,rgba(244,114,182,.05) 0%,transparent 55%)}}

/* ── header ── */
.header{{display:flex;align-items:center;justify-content:space-between;
  background:linear-gradient(135deg,rgba(167,139,250,.12),rgba(244,114,182,.08));
  border:1px solid rgba(167,139,250,.2);border-radius:20px;
  padding:18px 26px;margin-bottom:22px}}
.logo{{font-size:1.4rem;font-weight:800;letter-spacing:-.02em;
  background:linear-gradient(90deg,var(--purple),var(--pink));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.subtitle{{font-size:.72rem;color:var(--muted);margin-top:4px}}
.header-right{{text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:6px}}
.live-pill{{display:inline-flex;align-items:center;gap:7px;
  background:rgba(52,211,153,.1);border:1px solid rgba(52,211,153,.25);
  color:var(--green);border-radius:20px;padding:5px 14px;font-size:.72rem;font-weight:600}}
.dot{{width:7px;height:7px;border-radius:50%;background:var(--green);animation:blink 2s infinite}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.ts{{font-size:.7rem;color:var(--muted)}}

/* ── stat cards ── */
.cards{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:20px}}
@media(max-width:860px){{.cards{{grid-template-columns:repeat(3,1fr)}}}}
@media(max-width:520px){{.cards{{grid-template-columns:1fr 1fr}}}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:18px;
  padding:18px;position:relative;overflow:hidden;cursor:default;
  transition:border-color .25s,transform .2s}}
.card:hover{{border-color:rgba(167,139,250,.35);transform:translateY(-2px)}}
.card::after{{content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,var(--purple),var(--pink));
  transform:scaleX(0);transform-origin:left;transition:.3s}}
.card:hover::after{{transform:scaleX(1)}}
.card-icon{{font-size:1.25rem;margin-bottom:10px}}
.card-label{{font-size:.65rem;color:var(--muted);font-weight:600;
  text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}}
.card-val{{font-size:1.55rem;font-weight:700;line-height:1;letter-spacing:-.02em}}
.card-sub{{font-size:.72rem;color:var(--muted);margin-top:6px}}
.cg{{color:var(--green)}}.cr{{color:var(--red)}}
.cp{{color:var(--purple)}}.cy{{color:var(--yellow)}}.cb{{color:var(--blue)}}

/* ── sections ── */
.section{{background:var(--card);border:1px solid var(--border);
  border-radius:18px;padding:20px;margin-bottom:16px}}
.sec-title{{font-size:.72rem;font-weight:700;color:var(--muted);
  text-transform:uppercase;letter-spacing:.08em;
  display:flex;align-items:center;gap:8px;margin-bottom:18px}}
.sec-title b{{color:var(--text);font-weight:600}}

/* ── two-col layout ── */
.row2{{display:grid;grid-template-columns:1fr 1.5fr;gap:16px;margin-bottom:16px}}
@media(max-width:680px){{.row2{{grid-template-columns:1fr}}}}

/* ── gauge ── */
.gauge-shell{{background:var(--card2);border-radius:14px;padding:20px 18px 16px}}
.gauge-track{{position:relative;height:38px;border-radius:19px;overflow:visible;
  background:linear-gradient(90deg,
    rgba(248,113,113,.2) 0%,
    rgba(251,191,36,.2) 40%,
    rgba(52,211,153,.2) 100%)}}
.gauge-fill{{position:absolute;inset:0;border-radius:19px;
  background:linear-gradient(90deg,rgba(248,113,113,.3),rgba(167,139,250,.5),rgba(52,211,153,.6));
  transition:width .7s cubic-bezier(.4,0,.2,1);max-width:100%}}
.gmark{{position:absolute;top:-8px;width:2px;height:54px;border-radius:1px}}
.gneedle{{position:absolute;top:-10px;width:6px;height:58px;
  border-radius:3px;transform:translateX(-3px);
  background:linear-gradient(180deg,var(--purple),var(--pink));
  transition:left .7s cubic-bezier(.4,0,.2,1);
  box-shadow:0 0 14px rgba(167,139,250,.7)}}
.glabels{{display:grid;grid-template-columns:1fr 1fr 1fr;
  margin-top:10px;font-size:.67rem;color:var(--muted)}}
.glabels span:nth-child(2){{text-align:center}}
.glabels span:nth-child(3){{text-align:right}}
.gauge-num{{text-align:center;margin-top:18px}}
.gauge-num .big{{font-size:3.2rem;font-weight:800;line-height:1;letter-spacing:-.04em;
  background:linear-gradient(135deg,var(--purple),var(--pink));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;transition:all .3s}}
.gauge-num .big.fire{{background:linear-gradient(135deg,var(--green),var(--blue));-webkit-background-clip:text}}
.gauge-num .big.sell{{background:linear-gradient(135deg,var(--red),var(--yellow));-webkit-background-clip:text}}
.gauge-num .hint{{font-size:.75rem;color:var(--muted);margin-top:6px;min-height:1.2em}}
.tagrow{{display:flex;justify-content:center;gap:8px;margin-top:14px;flex-wrap:wrap}}
.tag{{padding:4px 12px;border-radius:20px;font-size:.68rem;font-weight:600;border:1px solid}}
.tag-g{{background:rgba(52,211,153,.1);border-color:rgba(52,211,153,.3);color:var(--green)}}
.tag-r{{background:rgba(248,113,113,.1);border-color:rgba(248,113,113,.3);color:var(--red)}}
.tag-p{{background:rgba(167,139,250,.1);border-color:rgba(167,139,250,.3);color:var(--purple)}}

/* ── table ── */
table{{width:100%;border-collapse:collapse;font-size:.75rem}}
thead th{{color:var(--muted);font-weight:600;text-align:left;padding:7px 10px;
  font-size:.63rem;text-transform:uppercase;letter-spacing:.05em;
  border-bottom:1px solid var(--border)}}
tbody td{{padding:9px 10px;border-bottom:1px solid rgba(255,255,255,.03)}}
tbody tr:last-child td{{border:none}}
tbody tr:hover{{background:rgba(167,139,250,.04)}}
.dir-s{{color:var(--red);font-weight:600}}
.dir-b{{color:var(--green);font-weight:600}}
.badge{{display:inline-block;padding:2px 9px;border-radius:10px;font-size:.65rem;font-weight:600}}
.badge-ok{{background:rgba(52,211,153,.12);color:var(--green)}}
.badge-fail{{background:rgba(248,113,113,.12);color:var(--red)}}
.empty{{text-align:center;padding:36px;color:var(--muted);font-size:.85rem}}

/* ── log ── */
.logbox{{background:#080613;border:1px solid var(--border);border-radius:12px;
  padding:14px;font-family:'SF Mono',Consolas,monospace;font-size:.68rem;
  line-height:1.75;overflow-y:auto;max-height:200px;color:#7c779e}}
.le{{color:#f87171}}.lw{{color:#fbbf24}}.larb{{color:#34d399}}.ldim{{color:#3d3958}}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <div>
    <div class="logo">ANTH 套利監控台</div>
    <div class="subtitle">Entropy&nbsp;(io:ANTH)&nbsp;&nbsp;&times;&nbsp;&nbsp;Lighter Robinhood&nbsp;(ANTHROPIC) &nbsp;|&nbsp; 中樞 {MIDLINE_BPS} bps &nbsp; 買觸發 {BUY_TRIGGER} bps &nbsp; 賣觸發 {SELL_TRIGGER} bps</div>
  </div>
  <div class="header-right">
    <div class="live-pill"><span class="dot"></span>即時監控中</div>
    <div class="ts" id="ts">—</div>
  </div>
</div>

<!-- Stat Cards -->
<div class="cards">
  <div class="card">
    <div class="card-icon">📈</div>
    <div class="card-label">Entropy 買一</div>
    <div class="card-val" id="e-bid">—</div>
    <div class="card-sub" id="e-ask">賣一 —</div>
  </div>
  <div class="card">
    <div class="card-icon">📉</div>
    <div class="card-label">Lighter 買一</div>
    <div class="card-val" id="l-bid">—</div>
    <div class="card-sub" id="l-ask">賣一 —</div>
  </div>
  <div class="card">
    <div class="card-icon">💱</div>
    <div class="card-label">可執行溢價（買 Entropy 方向）</div>
    <div class="card-val" id="spread">—</div>
    <div class="card-sub" id="spread-bps">賣邊 — bps</div>
  </div>
  <div class="card">
    <div class="card-icon">🔄</div>
    <div class="card-label">成交筆數</div>
    <div class="card-val cp" id="trade-cnt">0</div>
    <div class="card-sub" id="last-dir">尚無交易</div>
  </div>
  <div class="card">
    <div class="card-icon">💰</div>
    <div class="card-label">累計實際收益</div>
    <div class="card-val cg" id="fill-edge">$0.0000</div>
    <div class="card-sub" id="exp-edge">預期 $0.0000</div>
  </div>
</div>

<!-- Gauge + Chart -->
<div class="row2">
  <div class="section">
    <div class="sec-title">⚡ <b>買 Entropy 溢價儀表</b>&ensp;<span style="font-weight:400;color:var(--muted)">(lighter_bid / entropy_ask − 1)×10000</span></div>
    <div class="gauge-shell">
      <div class="gauge-track">
        <div class="gauge-fill" id="gfill" style="width:0%"></div>
        <div class="gmark" id="gm-buy" style="background:rgba(52,211,153,.8)"></div>
        <div class="gmark" id="gm-mid" style="background:rgba(167,139,250,.6)"></div>
        <div class="gmark" id="gm-sell" style="background:rgba(248,113,113,.8)"></div>
        <div class="gneedle" id="gneedle" style="left:50%"></div>
      </div>
      <div class="glabels">
        <span style="color:var(--green)">買觸發 {BUY_TRIGGER} bps</span>
        <span style="color:var(--purple)">中樞 {MIDLINE_BPS} bps</span>
        <span style="color:var(--red)">賣觸發 {SELL_TRIGGER} bps</span>
      </div>
    </div>
    <div class="gauge-num">
      <div class="big" id="g-num">—</div>
      <div class="hint" id="g-hint">等待資料…</div>
    </div>
    <div class="tagrow">
      <div class="tag tag-g">買 Entropy &ge; {BUY_TRIGGER} bps</div>
      <div class="tag tag-p">中樞 {MIDLINE_BPS} bps</div>
      <div class="tag tag-r">賣 Entropy sell_edge &ge; {SELL_TRIGGER} bps</div>
    </div>
  </div>

  <div class="section">
    <div class="sec-title">📊 <b>可執行溢價走勢</b>&ensp;近 60 分鐘</div>
    <canvas id="chart" height="210"></canvas>
  </div>
</div>

<!-- Trades -->
<div class="section">
  <div class="sec-title">🔄 <b>最近交易紀錄</b></div>
  <div id="trades-body"><div class="empty">尚無交易紀錄（記錄模式不執行真實下單）</div></div>
</div>

<!-- Log -->
<div class="section">
  <div class="sec-title">📋 <b>引擎日誌</b></div>
  <div class="logbox" id="logbox"><span class="ldim">等待資料…</span></div>
</div>

<script>
// 與 config.yaml 一致
const MIDLINE={MIDLINE_BPS}, SELL_TRIGGER={SELL_TRIGGER}, BUY_TRIGGER={BUY_TRIGGER};
// 儀表範圍：涵蓋兩個觸發閾值
const GAUGE_LO=-80, GAUGE_HI=110;
let chart=null;

function pct(v){{
  return Math.max(0, Math.min(100, (v - GAUGE_LO) / (GAUGE_HI - GAUGE_LO) * 100));
}}

function initChart(){{
  chart=new Chart(document.getElementById('chart').getContext('2d'),{{
    type:'line',
    data:{{labels:[],datasets:[
      {{label:'買 Entropy 溢價 bps',data:[],borderColor:'#a78bfa',
       backgroundColor:'rgba(167,139,250,.07)',borderWidth:2.5,
       pointRadius:2,pointBackgroundColor:'rgba(167,139,250,.9)',tension:.4,fill:true}},
      {{label:'賣觸發線 ({SELL_TRIGGER})',data:[],borderColor:'rgba(248,113,113,.65)',
       borderWidth:1.5,borderDash:[6,4],pointRadius:0,fill:false}},
      {{label:'買觸發線 ({BUY_TRIGGER})',data:[],borderColor:'rgba(52,211,153,.65)',
       borderWidth:1.5,borderDash:[6,4],pointRadius:0,fill:false}},
      {{label:'賣 Entropy 溢價 bps',data:[],borderColor:'rgba(248,113,113,.4)',
       borderWidth:1.5,borderDash:[3,3],pointRadius:0,fill:false}},
    ]}},
    options:{{
      responsive:true,animation:false,
      plugins:{{legend:{{labels:{{color:'#5e5a78',font:{{size:10}},boxWidth:14,usePointStyle:true}}}}}},
      scales:{{
        y:{{grid:{{color:'rgba(255,255,255,.04)'}},ticks:{{color:'#5e5a78',font:{{size:10}}}},border:{{color:'transparent'}}}},
        x:{{grid:{{display:false}},ticks:{{color:'#5e5a78',maxTicksLimit:8,font:{{size:10}}}},border:{{color:'transparent'}}}},
      }}
    }}
  }});
}}

function updateGauge(buyEdge, refPx){{
  // 在儀表上標示觸發閾值位置
  document.getElementById('gm-buy').style.left  = pct(BUY_TRIGGER)  + '%';
  document.getElementById('gm-mid').style.left  = pct(MIDLINE)      + '%';
  document.getElementById('gm-sell').style.left = pct(SELL_TRIGGER) + '%';
  if (buyEdge === null) return;
  const p = pct(buyEdge);
  document.getElementById('gneedle').style.left = p + '%';
  document.getElementById('gfill').style.width  = p + '%';

  const numEl  = document.getElementById('g-num');
  const hintEl = document.getElementById('g-hint');
  numEl.textContent = buyEdge.toFixed(2) + ' bps';

  // 買 Entropy 信號：buy_edge >= BUY_TRIGGER（目前幾乎常態觸發）
  const isBuy  = buyEdge >= BUY_TRIGGER;
  // 賣 Entropy 信號：sell_edge >= SELL_TRIGGER，此時 buy_edge 反向非常負
  const isSell = buyEdge <= -SELL_TRIGGER;

  numEl.className = 'big' + (isSell ? ' sell' : isBuy ? ' fire' : '');

  const liveRef = refPx || 2169;
  if (isSell) {{
    hintEl.textContent = '🔴 賣 Entropy 信號觸發！Bot 準備做空 Entropy';
    hintEl.style.color = 'var(--red)';
  }} else if (isBuy) {{
    const excess = (buyEdge - BUY_TRIGGER).toFixed(1);
    hintEl.textContent = `🟢 買 Entropy 信號觸發（超出觸發點 ${{excess}} bps）`;
    hintEl.style.color = 'var(--green)';
  }} else {{
    const diff = (BUY_TRIGGER - buyEdge).toFixed(1);
    const dollarApprox = (Math.abs(parseFloat(diff)) * liveRef / 10000).toFixed(2);
    hintEl.textContent = `距買入觸發還差 ${{diff}} bps（≈ $${{dollarApprox}}）`;
    hintEl.style.color = '';
  }}
}}

function render(d){{
  document.getElementById('ts').textContent = '更新 ' + d.ts;
  const mins = d.minutes;
  if (mins.length) {{
    const m = mins[mins.length-1];
    const eb = +m.entropy_bid || 0, ea = +m.entropy_ask || 0;
    const lb = +m.hedge_bid   || 0, la = +m.hedge_ask   || 0;
    const f = v => v ? '$' + v.toLocaleString('en', {{minimumFractionDigits:2, maximumFractionDigits:2}}) : '—';

    // Entropy 欄
    document.getElementById('e-bid').textContent = f(eb);
    document.getElementById('e-ask').textContent = '賣一 ' + f(ea);
    // Lighter 欄：正確顯示買一／賣一
    document.getElementById('l-bid').textContent = f(lb);
    document.getElementById('l-ask').textContent = '賣一 ' + f(la);

    // 可執行溢價（buy_edge = lighter_bid/entropy_ask - 1，正值代表 Lighter 較貴，買 Entropy 有利）
    const buy_edge  = lb && ea ? (lb / ea - 1) * 10000 : null;
    // 賣方溢價（sell_edge = entropy_bid/lighter_ask - 1，需 >= SELL_TRIGGER 才觸發賣 Entropy）
    const sell_edge = eb && la ? (eb / la - 1) * 10000 : null;
    // 每單位套利利潤（美元）= lighter_bid - entropy_ask
    const profitPerUnit = lb && ea ? lb - ea : null;

    const sEl = document.getElementById('spread');
    sEl.textContent = buy_edge !== null ? buy_edge.toFixed(2) + ' bps' : '—';
    sEl.className = 'card-val ' + (buy_edge >= BUY_TRIGGER ? 'cg' : buy_edge <= -SELL_TRIGGER ? 'cr' : 'cp');
    document.getElementById('spread-bps').textContent =
      sell_edge !== null ? '賣邊 ' + sell_edge.toFixed(2) + ' bps' : '賣邊 — bps';

    updateGauge(buy_edge, la || ea);

    // 圖表：近 60 分鐘 buy_edge & sell_edge 走勢
    const sl = mins.slice(-60);
    chart.data.labels = sl.map(r => r.time_utc ? r.time_utc.slice(11,16) : '');
    chart.data.datasets[0].data = sl.map(r => +(r.buy_edge_mean_bps)  || 0);  // 買 Entropy 溢價
    chart.data.datasets[1].data = sl.map(() => SELL_TRIGGER);                   // 賣觸發線 70
    chart.data.datasets[2].data = sl.map(() => BUY_TRIGGER);                    // 買觸發線 -40
    chart.data.datasets[3].data = sl.map(r => +(r.sell_edge_mean_bps) || 0);  // 賣 Entropy 溢價
    chart.update();
  }}

  const trades = d.trades;
  const ok = trades.filter(t => t.ok === '1');
  document.getElementById('trade-cnt').textContent = ok.length;
  if (ok.length) {{
    const l = ok[ok.length-1];
    document.getElementById('last-dir').textContent =
      l.direction === 'sell_entropy' ? '↓ 上次：賣E買L' : '↑ 上次：買E賣L';
  }}
  const fillSum = trades.reduce((s,t) => s + (+t.fill_edge_usd || 0), 0);
  const expSum  = trades.reduce((s,t) => s + (+t.exp_edge_usd  || 0), 0);
  const fEl = document.getElementById('fill-edge');
  fEl.textContent = (fillSum >= 0 ? '+' : '') + '$' + fillSum.toFixed(4);
  fEl.className = 'card-val ' + (fillSum >= 0 ? 'cg' : 'cr');
  document.getElementById('exp-edge').textContent = '預期 $' + expSum.toFixed(4);

  const tb = document.getElementById('trades-body');
  if (!trades.length) {{
    tb.innerHTML = '<div class="empty">尚無交易紀錄（記錄模式不執行真實下單）</div>';
  }} else {{
    const rows = [...trades].reverse().slice(0,12).map(t => {{
      const fill = +(t.fill_edge_usd) || 0;
      const sell = t.direction === 'sell_entropy';
      const ts   = new Date((+t.ts) * 1000).toLocaleTimeString('zh-TW');
      const isOk = t.ok === '1';
      const prem = +(t.marginal_premium_bps) || 0;
      return '<tr>'
        + '<td style="color:var(--muted)">' + ts + '</td>'
        + '<td class="' + (sell ? 'dir-s' : 'dir-b') + '">' + (sell ? '↓ 賣E買L' : '↑ 買E賣L') + '</td>'
        + '<td>$' + (+(t.buy_notional)||0).toFixed(0) + '</td>'
        + '<td>' + prem.toFixed(2) + ' bps</td>'
        + '<td class="' + (fill>=0?'cg':'cr') + '" style="font-weight:600">' + (fill>=0?'+':'') + '$' + fill.toFixed(4) + '</td>'
        + '<td><span class="badge ' + (isOk?'badge-ok':'badge-fail') + '">' + (isOk?'成功':'失敗') + '</span></td>'
        + '</tr>';
    }}).join('');
    tb.innerHTML = '<table><thead><tr>'
      + '<th>時間</th><th>方向</th><th>名義</th><th>溢價</th><th>實際收益</th><th>狀態</th>'
      + '</tr></thead><tbody>' + rows + '</tbody></table>';
  }}

  const lb = document.getElementById('logbox');
  if (!d.logs.length) {{
    lb.innerHTML = '<span class="ldim">等待日誌…</span>';
  }} else {{
    lb.innerHTML = d.logs.map(l => {{
      const s = l.replace(/</g, '&lt;');
      const c = l.includes('ERROR') || l.includes('CRITICAL') ? 'le'
               : l.includes('WARNING') ? 'lw'
               : l.includes('[ARB]') || l.includes('[SETTLED]') || l.includes('[HEDGE') ? 'larb' : '';
      return '<div class="' + c + '">' + s + '</div>';
    }}).join('');
    lb.scrollTop = lb.scrollHeight;
  }}
}}

async function refresh(){{
  try {{
    render(await (await fetch('/api/data')).json());
  }} catch(e) {{
    document.getElementById('ts').textContent = '⚠️ 連線失敗 ' + new Date().toLocaleTimeString();
  }}
}}

initChart();
refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            body = HTML.encode()
            self._send(200, "text/html; charset=utf-8", body)
        elif self.path == "/api/data":
            body = json.dumps({
                "minutes": _csv_tail(MINUTES_CSV, 60),
                "trades":  _csv_tail(TRADES_CSV,  20),
                "logs":    _log_tail(ENGINE_LOG,   20),
                "ts":      datetime.now().strftime("%H:%M:%S"),
            }).encode()
            self._send(200, "application/json", body)
        else:
            self._send(404, "text/plain", b"not found")

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"\n  ANTH 套利監控儀表板")
    print(f"  請在瀏覽器開啟 → http://localhost:{PORT}")
    print(f"  按 Ctrl+C 停止\n")
    HTTPServer(("", PORT), Handler).serve_forever()
