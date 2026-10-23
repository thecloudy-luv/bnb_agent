"""Dashboard HTML template and rendering for TiltBalance AI Agent."""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TiltBalance — AI Agent Dashboard</title>
  <link rel="icon" type="image/png" href="/logo.png">
  <style>
    :root {
      --bg: #0d1117;
      --card-bg: #161b22;
      --card-border: #30363d;
      --text: #c9d1d9;
      --text-muted: #8b949e;
      --text-bright: #f0f6fc;
      --primary: #f0b90b;
      --primary-dim: rgba(240, 185, 11, 0.15);
      --accent: #58a6ff;
      --success: #3fb950;
      --success-dim: rgba(63, 185, 80, 0.15);
      --warning: #d29922;
      --warning-dim: rgba(210, 153, 34, 0.15);
      --danger: #f85149;
      --code-bg: #090d13;
    }

    @media (prefers-color-scheme: light) {
      :root {
        --bg: #f6f8fa;
        --card-bg: #ffffff;
        --card-border: #d0d7de;
        --text: #24292f;
        --text-muted: #57606a;
        --text-bright: #1f2328;
        --primary: #c99400;
        --primary-dim: rgba(201, 148, 0, 0.12);
        --accent: #0969da;
        --success: #1a7f37;
        --success-dim: rgba(26, 127, 55, 0.12);
        --warning: #9a6700;
        --warning-dim: rgba(154, 103, 0, 0.12);
        --danger: #cf222e;
        --code-bg: #eaeef2;
      }
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 1.25rem;
      max-width: 1200px;
      margin: 0 auto;
    }

    header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 1.5rem;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 1rem;
    }

    .logo-img {
      width: 48px;
      height: 48px;
      border-radius: 8px;
      border: 1px solid var(--card-border);
      object-fit: cover;
    }

    .brand-text h1 {
      font-size: 1.4rem;
      color: var(--text-bright);
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .brand-text p {
      font-size: 0.85rem;
      color: var(--text-muted);
    }

    .badges {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: center;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.25rem 0.6rem;
      border-radius: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .badge-primary { background: var(--primary-dim); color: var(--primary); border: 1px solid var(--primary); }
    .badge-success { background: var(--success-dim); color: var(--success); border: 1px solid var(--success); }
    .badge-warning { background: var(--warning-dim); color: var(--warning); border: 1px solid var(--warning); }
    .badge-muted   { background: var(--code-bg); color: var(--text-muted); border: 1px solid var(--card-border); }

    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 1.25rem;
      margin-bottom: 1.5rem;
    }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 1.25rem;
    }

    .card-title {
      font-size: 1rem;
      font-weight: 600;
      color: var(--text-bright);
      margin-bottom: 1rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--card-border);
      padding-bottom: 0.5rem;
    }

    .kpi-row {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 0.75rem;
      margin-bottom: 0.75rem;
    }

    .kpi {
      background: var(--code-bg);
      padding: 0.75rem;
      border-radius: 6px;
      border: 1px solid var(--card-border);
    }

    .kpi-label {
      font-size: 0.75rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .kpi-value {
      font-size: 1.2rem;
      font-weight: 700;
      color: var(--text-bright);
      margin-top: 0.2rem;
    }

    .progress-bar-wrap {
      margin-top: 0.75rem;
    }

    .progress-label {
      display: flex;
      justify-content: space-between;
      font-size: 0.8rem;
      margin-bottom: 0.25rem;
    }

    .progress-bar {
      height: 8px;
      background: var(--code-bg);
      border-radius: 4px;
      overflow: hidden;
      border: 1px solid var(--card-border);
    }

    .progress-fill {
      height: 100%;
      background: var(--primary);
      width: 0%;
      transition: width 0.4s ease;
    }
    .progress-fill.done { background: var(--success); }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
      margin-top: 0.5rem;
    }

    th, td {
      text-align: left;
      padding: 0.6rem 0.5rem;
      border-bottom: 1px solid var(--card-border);
    }

    th {
      color: var(--text-muted);
      font-weight: 600;
      font-size: 0.75rem;
      text-transform: uppercase;
    }

    a {
      color: var(--accent);
      text-decoration: none;
    }
    a:hover { text-decoration: underline; }

    code {
      font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
      font-size: 0.78rem;
      background: var(--code-bg);
      padding: 0.15rem 0.35rem;
      border-radius: 4px;
      color: var(--text-bright);
    }

    .footer {
      text-align: center;
      font-size: 0.8rem;
      color: var(--text-muted);
      margin-top: 2rem;
      padding-top: 1rem;
      border-top: 1px solid var(--card-border);
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <img src="/logo.png" alt="TiltBalance Logo" class="logo-img">
      <div class="brand-text">
        <h1>TiltBalance <span style="font-size:0.8rem;font-weight:normal;color:var(--text-muted);">v0.1.0</span></h1>
        <p>Momentum-Tilted Portfolio Rebalancer &bull; BSC Testnet (97)</p>
      </div>
    </div>
    <div class="badges">
      <span id="badge-status" class="badge badge-success">&bull; Online</span>
      <span id="badge-loops" class="badge badge-muted">Loops: Off</span>
      <span class="badge badge-primary">Chain 97</span>
    </div>
  </header>

  <!-- Row 1: Strategy KPIs & Campaign Progress -->
  <div class="grid">

    <!-- Strategy KPIs -->
    <div class="card">
      <div class="card-title">
        <span>Portfolio Strategy (WBNB / BUSD)</span>
        <code id="pool-price">Price: -- BUSD</code>
      </div>
      <div class="kpi-row">
        <div class="kpi">
          <div class="kpi-label">Binance 24h Momentum</div>
          <div class="kpi-value" id="kpi-momentum">--%</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">Target BNB Weight</div>
          <div class="kpi-value" id="kpi-target">--%</div>
        </div>
      </div>
      <div class="kpi-row">
        <div class="kpi">
          <div class="kpi-label">Current BNB Weight</div>
          <div class="kpi-value" id="kpi-current">--%</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">Drift (|Current - Target|)</div>
          <div class="kpi-value" id="kpi-drift">--%</div>
        </div>
      </div>
      <div style="font-size:0.8rem;color:var(--text-muted);margin-top:0.5rem;" id="strategy-explanation">
        Awaiting latest evaluation cycle...
      </div>
    </div>

    <!-- Campaign Goal Progress -->
    <div class="card">
      <div class="card-title">
        <span>BNB Chain "Set and Earn" Goals</span>
        <span id="campaign-badge" class="badge badge-warning">Evaluating</span>
      </div>

      <div class="progress-bar-wrap">
        <div class="progress-label">
          <span>Distinct Independent Hires (Target: 3)</span>
          <strong id="prog-hires-txt">0 / 3</strong>
        </div>
        <div class="progress-bar">
          <div id="prog-hires-bar" class="progress-fill"></div>
        </div>
      </div>

      <div class="progress-bar-wrap">
        <div class="progress-label">
          <span>DEX Swaps via Router (Target: 5)</span>
          <strong id="prog-swaps-txt">0 / 5</strong>
        </div>
        <div class="progress-bar">
          <div id="prog-swaps-bar" class="progress-fill"></div>
        </div>
      </div>

      <div class="progress-bar-wrap">
        <div class="progress-label">
          <span>Active Swap Days (UTC) (Target: 3)</span>
          <strong id="prog-days-txt">0 / 3</strong>
        </div>
        <div class="progress-bar">
          <div id="prog-days-bar" class="progress-fill"></div>
        </div>
      </div>

      <div style="font-size:0.8rem;margin-top:0.75rem;color:var(--text-muted);">
        Total U Earned: <strong id="total-earned-u" style="color:var(--text-bright);">0.0000 U</strong>
      </div>
    </div>

  </div>

  <!-- Row 2: ERC-8183 Hires & Recent Rebalance Journal -->
  <div class="grid">

    <!-- ERC-8183 Hires -->
    <div class="card">
      <div class="card-title">
        <span>ERC-8183 Job Desk</span>
        <span id="hires-count" style="font-size:0.8rem;color:var(--text-muted);">0 jobs</span>
      </div>
      <div style="overflow-x:auto;">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Client</th>
              <th>Status</th>
              <th>Expiry</th>
              <th>Deliverable</th>
            </tr>
          </thead>
          <tbody id="jobs-table-body">
            <tr><td colspan="5" style="text-align:center;color:var(--text-muted);">No tracked jobs yet</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Recent Rebalance Swaps -->
    <div class="card">
      <div class="card-title">
        <span>Execution Journal &amp; Verifications</span>
        <span id="logs-count" style="font-size:0.8rem;color:var(--text-muted);">0 entries</span>
      </div>
      <div style="overflow-x:auto;">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Action</th>
              <th>Decision Hash</th>
              <th>Tx Hash</th>
            </tr>
          </thead>
          <tbody id="logs-table-body">
            <tr><td colspan="4" style="text-align:center;color:var(--text-muted);">No journal entries recorded</td></tr>
          </tbody>
        </table>
      </div>
    </div>

  </div>

  <div class="footer">
    <p>TiltBalance AI Agent &bull; Wallet: <code id="agent-wallet">--</code></p>
    <p style="margin-top:0.25rem;">Live market signals from Binance Vision API &bull; On-chain verification on PancakeSwap V2 &amp; ERC-8183 AgenticCommerce</p>
  </div>

  <script>
    async function updateDashboard() {
      try {
        const [statusRes, progRes] = await Promise.all([
          fetch('/status').then(r => r.json()).catch(() => null),
          fetch('/progress').then(r => r.json()).catch(() => null)
        ]);

        if (statusRes) {
          document.getElementById('agent-wallet').textContent = statusRes.wallet || '--';
          document.getElementById('badge-loops').textContent = statusRes.loops_enabled ? 'Loops: Active' : 'Loops: Off';
          document.getElementById('badge-loops').className = statusRes.loops_enabled ? 'badge badge-success' : 'badge badge-muted';

          // Strategy KPIs
          const last = statusRes.last_check;
          if (last) {
            const mom = last.momentum !== undefined ? (last.momentum * 100).toFixed(2) + '%' : '--%';
            const tgt = last.target_weight !== undefined ? (last.target_weight * 100).toFixed(1) + '%' : '--%';
            const cur = last.current_weight !== undefined ? (last.current_weight * 100).toFixed(1) + '%' : '--%';
            const drf = last.drift !== undefined ? (last.drift * 100).toFixed(2) + '%' : '--%';

            document.getElementById('kpi-momentum').textContent = mom;
            document.getElementById('kpi-target').textContent = tgt;
            document.getElementById('kpi-current').textContent = cur;
            document.getElementById('kpi-drift').textContent = drf;
            document.getElementById('strategy-explanation').textContent = last.reason || 'Optimal weight maintained.';
          }

          // Render jobs table
          const jobs = statusRes.jobs || [];
          document.getElementById('hires-count').textContent = jobs.length + ' jobs';
          const jBody = document.getElementById('jobs-table-body');
          if (jobs.length > 0) {
            jBody.innerHTML = jobs.map(j => {
              const clientShort = j.client ? j.client.slice(0, 6) + '...' + j.client.slice(-4) : '--';
              const deliv = j.deliverable_url ? `<a href="${j.deliverable_url}" target="_blank" rel="noopener">Link</a>` : '--';
              const rem = j.time_remaining_sec > 0 ? `${Math.round(j.time_remaining_sec / 60)}m` : 'Expired';
              return `<tr>
                <td><strong>#${j.id}</strong></td>
                <td><code>${clientShort}</code></td>
                <td><span class="badge ${j.status === 'COMPLETED' ? 'badge-success' : (j.status === 'FUNDED' ? 'badge-warning' : 'badge-primary')}">${j.status}</span></td>
                <td>${rem}</td>
                <td>${deliv}</td>
              </tr>`;
            }).join('');
          }

          // Render logs table
          const logs = statusRes.recent_logs || [];
          document.getElementById('logs-count').textContent = logs.length + ' entries';
          const lBody = document.getElementById('logs-table-body');
          if (logs.length > 0) {
            lBody.innerHTML = logs.slice(0, 8).map(l => {
              const dHash = l.decision_hash ? l.decision_hash.slice(0, 8) + '...' : '--';
              const txShort = l.tx_hash ? `<a href="${l.explorer_url}" target="_blank" rel="noopener">${l.tx_hash.slice(0, 8)}...</a>` : '--';
              const timeStr = l.timestamp ? l.timestamp.split('T')[1].slice(0, 8) : '--';
              return `<tr>
                <td>${timeStr}</td>
                <td><span class="badge ${l.action === 'none' ? 'badge-muted' : 'badge-primary'}">${l.action}</span></td>
                <td><code>${dHash}</code></td>
                <td>${txShort}</td>
              </tr>`;
            }).join('');
          }
        }

        if (progRes) {
          const hires = progRes.hires || {};
          const swaps = progRes.swaps || {};

          // Progress 1: Hires
          const hCount = hires.qualifying_count || 0;
          document.getElementById('prog-hires-txt').textContent = `${hCount} / 3`;
          const hPercent = Math.min(100, Math.round((hCount / 3) * 100));
          const hBar = document.getElementById('prog-hires-bar');
          hBar.style.width = hPercent + '%';
          if (hires.passed) hBar.classList.add('done');

          // Progress 2: Swaps
          const sCount = swaps.total_swaps || 0;
          document.getElementById('prog-swaps-txt').textContent = `${sCount} / 5`;
          const sPercent = Math.min(100, Math.round((sCount / 5) * 100));
          const sBar = document.getElementById('prog-swaps-bar');
          sBar.style.width = sPercent + '%';
          if (swaps.passed) sBar.classList.add('done');

          // Progress 3: Days
          const dCount = swaps.distinct_days_count || 0;
          document.getElementById('prog-days-txt').textContent = `${dCount} / 3`;
          const dPercent = Math.min(100, Math.round((dCount / 3) * 100));
          const dBar = document.getElementById('prog-days-bar');
          dBar.style.width = dPercent + '%';
          if (swaps.days_passed) dBar.classList.add('done');

          // Campaign badge
          const cBadge = document.getElementById('campaign-badge');
          if (progRes.campaign_ready) {
            cBadge.className = 'badge badge-success';
            cBadge.textContent = 'All Criteria Met';
          } else {
            cBadge.className = 'badge badge-warning';
            cBadge.textContent = 'In Progress';
          }

          document.getElementById('total-earned-u').textContent = (hires.total_earned_u || 0).toFixed(4) + ' U';
        }

      } catch (err) {
        console.warn('Dashboard poll error:', err);
      }
    }

    updateDashboard();
    setInterval(updateDashboard, 10000);
  </script>
</body>
</html>
"""
