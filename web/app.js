// One Piece Character Network - Interactive Visualization
// ========================================================

let DATA = null;
let RASTER = null;
let cy = null;
let egoCy = null;
let rankingsChart = null;

// ---- Data Loading ----
async function loadData() {
    const status = document.getElementById('loading-status');
    status.textContent = 'Loading network data...';
    const resp = await fetch('data/network.json');
    DATA = await resp.json();
    status.textContent = 'Loading raster data...';
    const resp2 = await fetch('data/raster.json');
    RASTER = await resp2.json();
    status.textContent = 'Initializing...';
}

// ---- Navigation ----
function setupNav() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
            btn.classList.add('active');
            const section = document.getElementById(btn.dataset.section);
            section.classList.add('active');
            // Lazy init
            if (btn.dataset.section === 'network' && !cy) initGraph();
            if (btn.dataset.section === 'raster') drawRaster();
        });
    });
}

// ---- Overview ----
function renderOverview() {
    const s = DATA.stats;
    const grid = document.getElementById('stats-grid');
    const stats = [
        { value: s.num_characters.toLocaleString(), label: 'Characters' },
        { value: s.num_edges.toLocaleString(), label: 'Connections' },
        { value: s.mean_degree, label: 'Mean Degree' },
        { value: s.avg_path_length, label: 'Avg Path Length' },
        { value: s.diameter, label: 'Diameter' },
        { value: s.avg_clustering, label: 'Clustering Coeff.' },
        { value: s.modularity, label: 'Modularity' },
        { value: s.num_communities, label: 'Communities' },
    ];
    grid.innerHTML = stats.map(s =>
        `<div class="stat-card"><span class="value">${s.value}</span><span class="label">${s.label}</span></div>`
    ).join('');

    // Degree distribution chart
    renderDegreeChart();

    // Top pairs table
    renderTopPairs();
}

function renderDegreeChart() {
    const ctx = document.getElementById('degree-chart').getContext('2d');
    const dd = DATA.degree_distribution;
    // Bin the degree distribution
    const maxDeg = Math.max(...dd.map(d => d.degree));
    const binSize = Math.max(1, Math.floor(maxDeg / 40));
    const bins = {};
    dd.forEach(d => {
        const bin = Math.floor(d.degree / binSize) * binSize;
        bins[bin] = (bins[bin] || 0) + d.count;
    });
    const labels = Object.keys(bins).map(Number).sort((a, b) => a - b);
    const values = labels.map(l => bins[l]);

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels.map(l => l.toString()),
            datasets: [{
                data: values,
                backgroundColor: 'rgba(0,191,255,0.6)',
                borderColor: 'rgba(0,191,255,1)',
                borderWidth: 1,
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    title: { display: true, text: 'Degree', color: '#888' },
                    ticks: { color: '#888', maxTicksLimit: 20 },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                },
                y: {
                    title: { display: true, text: 'Count', color: '#888' },
                    ticks: { color: '#888' },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                }
            }
        }
    });
}

function renderTopPairs() {
    const container = document.getElementById('top-pairs-table');
    // Filter out pairs with very low co-appearances (artifact pairs)
    const pairs = DATA.top_pairs.filter(p => p.co_appearances >= 10).slice(0, 30);
    container.innerHTML = `<table>
        <thead><tr><th>#</th><th>Character 1</th><th>Character 2</th><th>Friendship</th><th>Shared Eps</th></tr></thead>
        <tbody>${pairs.map((p, i) => `<tr>
            <td class="rank-num">${i + 1}</td>
            <td>${p.char1}</td><td>${p.char2}</td>
            <td>${p.friendship.toFixed(3)}</td><td>${p.co_appearances}</td>
        </tr>`).join('')}</tbody>
    </table>`;
}

// ---- Network Graph ----
function initGraph() {
    const status = document.getElementById('graph-status');
    status.textContent = 'Building graph...';

    const threshold = document.getElementById('threshold-select').value;
    const minEps = parseInt(document.getElementById('min-episodes-slider').value);
    buildGraph(threshold, minEps);

    // Event listeners
    document.getElementById('threshold-select').addEventListener('change', () => rebuildGraph());
    document.getElementById('min-episodes-slider').addEventListener('input', (e) => {
        document.getElementById('min-episodes-val').textContent = e.target.value;
    });
    document.getElementById('min-episodes-slider').addEventListener('change', () => rebuildGraph());
    document.getElementById('color-by').addEventListener('change', () => recolorGraph());
    document.getElementById('size-by').addEventListener('change', () => resizeGraph());
    document.getElementById('layout-select').addEventListener('change', () => relayoutGraph());
    document.getElementById('reset-graph-btn').addEventListener('click', () => {
        if (cy) cy.fit(undefined, 30);
    });
    document.getElementById('close-panel').addEventListener('click', () => {
        document.getElementById('node-info-panel').classList.add('hidden');
    });
}

function buildGraph(threshold, minEps) {
    const status = document.getElementById('graph-status');
    const edges = DATA.edges[threshold] || [];
    const filteredNodes = DATA.nodes.filter(n => n.episodes >= minEps);
    const nodeIds = new Set(filteredNodes.map(n => n.id));
    const filteredEdges = edges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));

    status.textContent = `Building: ${filteredNodes.length} nodes, ${filteredEdges.length} edges...`;

    const elements = [];
    const colorBy = document.getElementById('color-by').value;
    const sizeBy = document.getElementById('size-by').value;

    // Compute size range
    const sizeValues = filteredNodes.map(n => n[sizeBy] || n.episodes);
    const maxSize = Math.max(...sizeValues);
    const minSize = Math.min(...sizeValues);

    filteredNodes.forEach(n => {
        const sizeVal = n[sizeBy] || n.episodes;
        const normSize = maxSize > minSize ? (sizeVal - minSize) / (maxSize - minSize) : 0.5;
        const nodeSize = 8 + normSize * 40;

        elements.push({
            group: 'nodes',
            data: {
                id: n.id,
                label: n.label,
                color: getNodeColor(n, colorBy),
                size: nodeSize,
                ...n
            }
        });
    });

    filteredEdges.forEach(e => {
        elements.push({
            group: 'edges',
            data: {
                source: e.source,
                target: e.target,
                weight: e.weight,
            }
        });
    });

    if (cy) cy.destroy();

    cy = cytoscape({
        container: document.getElementById('cy'),
        elements: elements,
        style: [
            {
                selector: 'node',
                style: {
                    'background-color': 'data(color)',
                    'label': 'data(label)',
                    'width': 'data(size)',
                    'height': 'data(size)',
                    'font-size': 8,
                    'color': '#ccc',
                    'text-valign': 'bottom',
                    'text-margin-y': 4,
                    'min-zoomed-font-size': 10,
                    'text-outline-width': 2,
                    'text-outline-color': '#0a0a0f',
                }
            },
            {
                selector: 'edge',
                style: {
                    'width': 'mapData(weight, 0, 1, 0.3, 3)',
                    'line-color': 'rgba(255,255,255,0.8)',
                    'curve-style': 'haystack',
                }
            },
            {
                selector: 'node:selected',
                style: {
                    'border-width': 3,
                    'border-color': '#ffd93d',
                    'font-size': 14,
                    'color': '#fff',
                    'z-index': 999,
                }
            },
            {
                selector: 'node.highlighted',
                style: {
                    'border-width': 2,
                    'border-color': '#ffd93d',
                    'opacity': 1,
                    'z-index': 100,
                }
            },
            {
                selector: 'node.dimmed',
                style: {
                    'opacity': 0.1,
                }
            },
            {
                selector: 'edge.highlighted',
                style: {
                    'line-color': 'rgba(255, 217, 61, 0.5)',
                    'width': 2,
                    'z-index': 100,
                }
            },
            {
                selector: 'edge.dimmed',
                style: {
                    'opacity': 0.03,
                }
            }
        ],
        layout: getLayoutOptions(),
        wheelSensitivity: 0.3,
        maxZoom: 10,
        minZoom: 0.1,
    });

    // Node click handler
    cy.on('tap', 'node', function (evt) {
        const node = evt.target;
        showNodeInfo(node.data());
        highlightNeighbors(node);
    });

    cy.on('tap', function (evt) {
        if (evt.target === cy) {
            document.getElementById('node-info-panel').classList.add('hidden');
            cy.elements().removeClass('highlighted dimmed');
        }
    });

    status.textContent = `Showing ${filteredNodes.length} characters, ${filteredEdges.length} connections (threshold: ${threshold})`;
}

function getNodeColor(node, colorBy) {
    if (colorBy === 'community') return node.community_color;
    if (colorBy === 'faction') {
        const factionColors = {
            'Straw Hat Pirates': '#00bfff', 'Marines': '#2980b3',
            'Beasts Pirates': '#c0392b', 'Charlotte Family': '#ff69b4',
            'Whitebeard Pirates': '#f39c12', 'World Government': '#8e44ad',
            'Revolutionary Army': '#27ae60', 'Baroque Works': '#d4ac0d',
            'Blackbeard Pirates': '#646464', 'Donquixote Pirates': '#e74c3c',
            'Roger Pirates': '#d4a017',
        };
        return factionColors[node.faction] || '#444';
    }
    if (colorBy === 'episodes') {
        const t = Math.min(node.episodes / 500, 1);
        const r = Math.round(255 * t);
        const b = Math.round(255 * (1 - t));
        return `rgb(${r},${Math.round(100 * t)},${b})`;
    }
    if (colorBy === 'betweenness') {
        const t = Math.min(node.betweenness / 0.05, 1);
        const r = Math.round(255 * t);
        return `rgb(${r},${Math.round(200 * (1 - t))},${Math.round(50 + 200 * (1 - t))})`;
    }
    return '#00bfff';
}

function getLayoutOptions() {
    const layout = document.getElementById('layout-select').value;
    if (layout === 'cose') {
        return {
            name: 'cose',
            animate: false,
            nodeRepulsion: 800000,
            idealEdgeLength: 80,
            gravity: 0.3,
            numIter: 500,
            nodeDimensionsIncludeLabels: false,
        };
    }
    if (layout === 'concentric') {
        return {
            name: 'concentric',
            animate: false,
            concentric: function (node) { return node.data('episodes'); },
            levelWidth: function () { return 8; },
        };
    }
    return { name: layout, animate: false };
}

function rebuildGraph() {
    const threshold = document.getElementById('threshold-select').value;
    const minEps = parseInt(document.getElementById('min-episodes-slider').value);
    buildGraph(threshold, minEps);
}

function recolorGraph() {
    if (!cy) return;
    const colorBy = document.getElementById('color-by').value;
    cy.nodes().forEach(node => {
        node.data('color', getNodeColor(node.data(), colorBy));
    });
}

function resizeGraph() {
    if (!cy) return;
    const sizeBy = document.getElementById('size-by').value;
    const nodes = cy.nodes();
    const values = nodes.map(n => n.data(sizeBy) || n.data('episodes'));
    const maxVal = Math.max(...values);
    const minVal = Math.min(...values);
    nodes.forEach(n => {
        const val = n.data(sizeBy) || n.data('episodes');
        const norm = maxVal > minVal ? (val - minVal) / (maxVal - minVal) : 0.5;
        n.data('size', 8 + norm * 40);
    });
}

function relayoutGraph() {
    if (!cy) return;
    cy.layout(getLayoutOptions()).run();
}

function highlightNeighbors(node) {
    cy.elements().removeClass('highlighted dimmed');
    const neighborhood = node.neighborhood().add(node);
    cy.elements().not(neighborhood).addClass('dimmed');
    neighborhood.addClass('highlighted');
    node.addClass('highlighted');
}

function showNodeInfo(data) {
    const panel = document.getElementById('node-info-panel');
    panel.classList.remove('hidden');
    document.getElementById('panel-name').textContent = data.label;

    // Find connections for this character
    const edges = DATA.edges['0.1'] || DATA.edges['0.2'] || [];
    const connections = edges
        .filter(e => e.source === data.id || e.target === data.id)
        .map(e => {
            const otherId = e.source === data.id ? e.target : e.source;
            const other = DATA.nodes.find(n => n.id === otherId);
            return { name: other ? other.label : otherId, weight: e.weight };
        })
        .sort((a, b) => b.weight - a.weight)
        .slice(0, 15);

    document.getElementById('panel-content').innerHTML = `
        <div class="stat-row"><span class="label">Faction</span><span>${data.faction}</span></div>
        <div class="stat-row"><span class="label">Episodes</span><span>${data.episodes}</span></div>
        <div class="stat-row"><span class="label">Connections</span><span>${data.degree}</span></div>
        <div class="stat-row"><span class="label">Betweenness</span><span>${data.betweenness?.toFixed(4)}</span></div>
        <div class="stat-row"><span class="label">Eigenvector</span><span>${data.eigenvector?.toFixed(4)}</span></div>
        <div class="stat-row"><span class="label">Clustering</span><span>${data.clustering?.toFixed(4)}</span></div>
        <div class="stat-row"><span class="label">Community</span><span style="color:${data.community_color}">#${data.community}</span></div>
        <h4 style="margin-top:14px;font-size:14px;color:#ffd93d">Strongest Connections</h4>
        <ul class="connections-list">
            ${connections.map(c => `<li><span>${c.name}</span><span style="color:var(--accent)">${c.weight.toFixed(3)}</span></li>`).join('')}
        </ul>
    `;
}

// ---- Character Raster ----
let _rasterNodes = null; // cached for tooltip
let _rasterCellW = 4;
let _rasterCellH = 12;
let _rasterMaxEp = 1156;

function drawRaster() {
    const dataCanvas = document.getElementById('raster-canvas');
    const labelCanvas = document.getElementById('raster-labels-canvas');
    const dataCtx = dataCanvas.getContext('2d');
    const labelCtx = labelCanvas.getContext('2d');
    const search = document.getElementById('raster-search').value.toLowerCase();
    const count = parseInt(document.getElementById('raster-count').value);
    const cellW = parseInt(document.getElementById('raster-cell-size').value);
    const cellH = Math.max(cellW * 3, 10);
    const labelW = 180;

    // Filter & sort nodes (already sorted by episodes desc from data)
    let nodes = [...DATA.nodes];
    if (search) {
        nodes = nodes.filter(n => n.id.toLowerCase().includes(search));
    }
    nodes = nodes.slice(0, count);
    _rasterNodes = nodes;
    _rasterCellW = cellW;
    _rasterCellH = cellH;

    const maxEp = Math.max(...Object.values(RASTER).flat());
    _rasterMaxEp = maxEp;
    const dataWidth = maxEp * cellW + 40;
    const height = nodes.length * cellH + 60;
    const dpr = window.devicePixelRatio || 2;

    // --- Labels canvas (fixed left column) ---
    labelCanvas.width = labelW * dpr;
    labelCanvas.height = height * dpr;
    labelCanvas.style.width = labelW + 'px';
    labelCanvas.style.height = height + 'px';
    labelCtx.scale(dpr, dpr);

    labelCtx.fillStyle = '#12121a';
    labelCtx.fillRect(0, 0, labelW, height);

    // Title area on labels side
    labelCtx.fillStyle = '#e0e0e8';
    labelCtx.font = 'bold 11px Inter, sans-serif';
    labelCtx.textAlign = 'right';
    labelCtx.fillText('Character', labelW - 8, 16);

    nodes.forEach((node, i) => {
        const y = i * cellH + 40;

        // Alternating row bg
        if (i % 2 === 0) {
            labelCtx.fillStyle = 'rgba(255,255,255,0.015)';
            labelCtx.fillRect(0, y, labelW, cellH);
        }

        // Character name
        labelCtx.fillStyle = node.community_color || '#888';
        labelCtx.font = `${Math.min(cellH - 2, 11)}px Inter, sans-serif`;
        labelCtx.textAlign = 'right';
        const displayName = node.id.length > 22 ? node.id.substring(0, 20) + '...' : node.id;
        labelCtx.fillText(displayName, labelW - 8, y + cellH - 2);
    });

    // Right edge line on labels
    labelCtx.strokeStyle = 'rgba(255,255,255,0.08)';
    labelCtx.beginPath();
    labelCtx.moveTo(labelW - 0.5, 0);
    labelCtx.lineTo(labelW - 0.5, height);
    labelCtx.stroke();

    // --- Data canvas (scrollable episodes) ---
    dataCanvas.width = dataWidth * dpr;
    dataCanvas.height = height * dpr;
    dataCanvas.style.width = dataWidth + 'px';
    dataCanvas.style.height = height + 'px';
    dataCtx.scale(dpr, dpr);

    dataCtx.fillStyle = '#0a0a0f';
    dataCtx.fillRect(0, 0, dataWidth, height);

    // Episode axis at top
    dataCtx.fillStyle = '#888';
    dataCtx.font = '9px Inter, sans-serif';
    dataCtx.textAlign = 'center';
    for (let ep = 50; ep <= maxEp; ep += 50) {
        const x = (ep - 1) * cellW;
        dataCtx.fillText(ep.toString(), x, 32);
        // Subtle gridline
        dataCtx.strokeStyle = 'rgba(255,255,255,0.03)';
        dataCtx.beginPath();
        dataCtx.moveTo(x, 38);
        dataCtx.lineTo(x, height);
        dataCtx.stroke();
    }

    // Title on data side
    dataCtx.fillStyle = '#e0e0e8';
    dataCtx.font = 'bold 11px Inter, sans-serif';
    dataCtx.textAlign = 'left';
    dataCtx.fillText(`${nodes.length} characters \u00d7 ${maxEp} episodes`, 4, 16);

    // Draw each character's episode data
    nodes.forEach((node, i) => {
        const y = i * cellH + 40;

        // Alternating row bg
        if (i % 2 === 0) {
            dataCtx.fillStyle = 'rgba(255,255,255,0.015)';
            dataCtx.fillRect(0, y, dataWidth, cellH);
        }

        // Episode cells
        const eps = RASTER[node.id] || [];
        dataCtx.fillStyle = node.community_color || '#00bfff';
        eps.forEach(ep => {
            const x = (ep - 1) * cellW;
            dataCtx.fillRect(x, y, cellW - 1, cellH - 1);
        });
    });

    // Setup listeners once
    if (!dataCanvas._listenersSet) {
        dataCanvas._listenersSet = true;
        document.getElementById('raster-search').addEventListener('input', () => drawRaster());
        document.getElementById('raster-count').addEventListener('change', () => drawRaster());
        document.getElementById('raster-cell-size').addEventListener('change', () => drawRaster());

        // Tooltip on hover over data canvas
        dataCanvas.addEventListener('mousemove', (e) => {
            const rect = dataCanvas.getBoundingClientRect();
            const x = (e.clientX - rect.left);
            const y = (e.clientY - rect.top);
            const charIdx = Math.floor((y - 40) / _rasterCellH);
            const ep = Math.floor(x / _rasterCellW) + 1;
            const tooltip = document.getElementById('raster-tooltip');

            if (_rasterNodes && charIdx >= 0 && charIdx < _rasterNodes.length && ep > 0 && ep <= _rasterMaxEp) {
                const node = _rasterNodes[charIdx];
                const eps = RASTER[node.id] || [];
                const appears = eps.includes(ep);
                tooltip.classList.remove('hidden');
                tooltip.style.left = (e.clientX + 12) + 'px';
                tooltip.style.top = (e.clientY - 10) + 'px';
                tooltip.innerHTML = `<strong>${node.id}</strong><br>Episode ${ep} \u00b7 ${node.episodes} total eps<br>${appears ? '<span style="color:#6bcb77">&#10003; Appears</span>' : '<span style="color:#ff6b6b">&#10007; Does not appear</span>'}`;
            } else {
                tooltip.classList.add('hidden');
            }
        });
        dataCanvas.addEventListener('mouseleave', () => {
            document.getElementById('raster-tooltip').classList.add('hidden');
        });

        // Also show tooltip on label hover
        labelCanvas.addEventListener('mousemove', (e) => {
            const rect = labelCanvas.getBoundingClientRect();
            const y = (e.clientY - rect.top);
            const charIdx = Math.floor((y - 40) / _rasterCellH);
            const tooltip = document.getElementById('raster-tooltip');

            if (_rasterNodes && charIdx >= 0 && charIdx < _rasterNodes.length) {
                const node = _rasterNodes[charIdx];
                const eps = RASTER[node.id] || [];
                tooltip.classList.remove('hidden');
                tooltip.style.left = (e.clientX + 12) + 'px';
                tooltip.style.top = (e.clientY - 10) + 'px';
                tooltip.innerHTML = `<strong>${node.id}</strong><br>${eps.length} episodes<br>Faction: ${node.faction}`;
            } else {
                tooltip.classList.add('hidden');
            }
        });
        labelCanvas.addEventListener('mouseleave', () => {
            document.getElementById('raster-tooltip').classList.add('hidden');
        });
    }
}

// ---- Communities ----
function renderCommunities() {
    const grid = document.getElementById('communities-grid');
    grid.innerHTML = DATA.communities.map(c => {
        // Find the community color from nodes
        const node = DATA.nodes.find(n => n.community === c.id);
        const color = node ? node.community_color : '#444';
        return `<div class="community-card">
            <div class="comm-header">
                <div class="comm-dot" style="background:${color}"></div>
                <div>
                    <strong>Community #${c.id}</strong>
                    <div class="comm-size">${c.size} characters · Avg ${c.avg_episodes} episodes · ${c.top_faction}</div>
                </div>
            </div>
            <div class="members">
                ${c.top_members.map(m => `<span class="member-tag">${m}</span>`).join('')}
                ${c.size > 8 ? `<span class="member-tag" style="color:var(--text-dim)">+${c.size - 8} more</span>` : ''}
            </div>
        </div>`;
    }).join('');
}

// ---- Rankings ----
function renderRankings() {
    const metric = document.getElementById('ranking-metric').value;
    const data = DATA.rankings[metric];
    if (!data) return;

    const table = document.getElementById('rankings-table');
    const metricLabel = {
        by_episodes: 'Episodes', by_degree: 'Degree',
        by_betweenness: 'Betweenness', by_eigenvector: 'Eigenvector'
    }[metric];

    table.innerHTML = `<table>
        <thead><tr><th>#</th><th>Character</th><th>${metricLabel}</th></tr></thead>
        <tbody>${data.map((d, i) => `<tr>
            <td class="rank-num">${i + 1}</td>
            <td>${d.label}</td>
            <td>${typeof d.value === 'number' && d.value < 1 ? d.value.toFixed(4) : d.value}</td>
        </tr>`).join('')}</tbody>
    </table>`;

    // Bar chart
    const top20 = data.slice(0, 20);
    const ctx = document.getElementById('rankings-bar-chart').getContext('2d');
    if (rankingsChart) rankingsChart.destroy();
    rankingsChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: top20.map(d => d.label),
            datasets: [{
                data: top20.map(d => d.value),
                backgroundColor: top20.map((_, i) => {
                    const t = i / 20;
                    return `rgba(${Math.round(0 + 255 * t)}, ${Math.round(191 - 100 * t)}, ${Math.round(255 - 200 * t)}, 0.7)`;
                }),
                borderWidth: 0,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    title: { display: true, text: metricLabel, color: '#888' },
                    ticks: { color: '#888' },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                },
                y: {
                    ticks: { color: '#ccc', font: { size: 10 } },
                    grid: { display: false },
                }
            }
        }
    });

    // Explanation
    const explanations = {
        by_episodes: `<h4>Episode Count — N<sub>i</sub></h4>
            <p>The total number of episodes a character appears in: <strong>N<sub>i</sub> = Σ<sub>e</sub> a<sub>i</sub>(e)</strong></p>
            <p>This is the simplest measure of prominence. Luffy tops the list with 1,098 episodes — he's absent from fewer than 60 total.</p>
            <p>The Straw Hats dominate here, but note some characters like Nico Robin and Jinbe rank lower than their narrative importance might suggest — they joined the crew later, so their raw count is lower.</p>`,
        by_degree: `<h4>Degree — k<sub>i</sub></h4>
            <p><strong>k<sub>i</sub> = |{j : N<sub>ij</sub> > 0}|</strong> — the count of distinct characters that share at least one episode with character <em>i</em>.</p>
            <p>Degree centrality normalizes this: <strong>C<sub>D</sub>(i) = k<sub>i</sub> / (N − 1)</strong>.</p>
            <p>Luffy's degree of 1,109 means he has co-appeared with virtually every character in the series. Characters with high degree but moderate episode count (like Buggy) are "connectors" who bridge many story arcs.</p>`,
        by_betweenness: `<h4>Betweenness — C<sub>B</sub>(i)</h4>
            <p><strong>C<sub>B</sub>(i) = Σ<sub>s≠i≠t</sub> σ<sub>st</sub>(i) / σ<sub>st</sub></strong>, normalized by (N−1)(N−2)/2.</p>
            <p>This measures how often a character lies on shortest paths between other characters. High betweenness = a bridge between otherwise disconnected groups.</p>
            <p>A character can have high betweenness with moderate episode count if they uniquely link separate story arcs. The Straw Hats naturally rank high because they travel between many otherwise isolated communities.</p>`,
        by_eigenvector: `<h4>Eigenvector — C<sub>E</sub>(i)</h4>
            <p>Defined by the eigenvalue equation: <strong>A · x = λ<sub>max</sub> · x</strong>, where C<sub>E</sub>(i) = x<sub>i</sub>.</p>
            <p>A character scores high not just by having many connections, but by being connected to other <strong>well-connected</strong> characters. It's recursive: your importance depends on the importance of your neighbors.</p>
            <p>Interestingly, this metric can elevate characters who aren't Straw Hats but are deeply embedded in important clusters (e.g., Whitebeard's crew members).</p>`,
    };
    document.getElementById('metric-explanation').innerHTML = explanations[metric] || '';

    if (!document.getElementById('ranking-metric')._listening) {
        document.getElementById('ranking-metric')._listening = true;
        document.getElementById('ranking-metric').addEventListener('change', () => renderRankings());
    }
}

// ---- Character Explorer ----
function setupExplorer() {
    const input = document.getElementById('explorer-search');
    const datalist = document.getElementById('char-list');

    // Populate datalist
    datalist.innerHTML = DATA.nodes.map(n =>
        `<option value="${n.label}">`
    ).join('');

    input.addEventListener('change', () => {
        const name = input.value;
        const node = DATA.nodes.find(n => n.label === name);
        if (node) showExplorer(node);
    });
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const name = input.value;
            const node = DATA.nodes.find(n => n.label.toLowerCase() === name.toLowerCase());
            if (node) showExplorer(node);
        }
    });
}

function showExplorer(node) {
    const content = document.getElementById('explorer-content');
    content.classList.remove('hidden');

    // Stats
    const statsGrid = document.getElementById('explorer-stats');
    const stats = [
        { value: node.episodes, label: 'Episodes' },
        { value: node.degree, label: 'Connections' },
        { value: node.faction, label: 'Faction' },
        { value: node.betweenness.toFixed(4), label: 'Betweenness' },
        { value: node.eigenvector.toFixed(4), label: 'Eigenvector' },
        { value: `#${node.community}`, label: 'Community' },
    ];
    statsGrid.innerHTML = stats.map(s =>
        `<div class="stat-card"><span class="value" style="font-size:${typeof s.value === 'string' && s.value.length > 8 ? '16' : '24'}px">${s.value}</span><span class="label">${s.label}</span></div>`
    ).join('');

    // Timeline
    drawExplorerTimeline(node);

    // Connections table
    const allEdges = DATA.edges['0.05'] || DATA.edges['0.1'] || [];
    const connections = allEdges
        .filter(e => e.source === node.id || e.target === node.id)
        .map(e => {
            const otherId = e.source === node.id ? e.target : e.source;
            const other = DATA.nodes.find(n => n.id === otherId);
            return { name: other ? other.label : otherId, id: otherId, weight: e.weight, coApp: e.co_appearances };
        })
        .sort((a, b) => b.weight - a.weight)
        .slice(0, 30);

    document.getElementById('explorer-connections').innerHTML = `<table>
        <thead><tr><th>#</th><th>Character</th><th>Friendship</th><th>Shared Eps</th></tr></thead>
        <tbody>${connections.map((c, i) => `<tr>
            <td class="rank-num">${i + 1}</td><td>${c.name}</td>
            <td>${c.weight.toFixed(3)}</td><td>${c.coApp}</td>
        </tr>`).join('')}</tbody>
    </table>`;

    // Ego network
    buildEgoNetwork(node, connections);
}

function drawExplorerTimeline(node) {
    const eps = RASTER[node.id] || [];
    const canvas = document.getElementById('explorer-timeline');
    const ctx = canvas.getContext('2d');

    // Create binary presence data per episode
    const maxEp = 1156;
    const binSize = 5;
    const bins = [];
    for (let i = 0; i < maxEp; i += binSize) {
        const count = eps.filter(e => e > i && e <= i + binSize).length;
        bins.push(count);
    }

    if (canvas._chart) canvas._chart.destroy();
    canvas._chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: bins.map((_, i) => (i * binSize + 1).toString()),
            datasets: [{
                data: bins,
                backgroundColor: node.community_color || '#00bfff',
                borderWidth: 0,
                barPercentage: 1.0,
                categoryPercentage: 1.0,
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false },
                title: { display: true, text: `${node.label} — ${eps.length} episodes`, color: '#ccc' }
            },
            scales: {
                x: {
                    ticks: { color: '#888', maxTicksLimit: 12 },
                    grid: { display: false },
                    title: { display: true, text: 'Episode', color: '#888' }
                },
                y: {
                    ticks: { color: '#888', stepSize: 1 },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    title: { display: true, text: 'Appearances per 5 episodes', color: '#888' }
                }
            }
        }
    });
}

function buildEgoNetwork(centerNode, connections) {
    if (egoCy) egoCy.destroy();

    // Ensure the container is visible and has dimensions
    const container = document.getElementById('ego-cy');
    container.style.minHeight = '500px';
    container.style.display = 'block';

    const elements = [];
    const connIds = new Set(connections.map(c => c.id));

    // Center node
    elements.push({
        group: 'nodes',
        data: {
            id: centerNode.id, label: centerNode.label,
            color: '#ffd93d', size: 50,
        }
    });

    // Connected nodes
    connections.forEach(c => {
        const other = DATA.nodes.find(n => n.id === c.id);
        if (!other) return;
        elements.push({
            group: 'nodes',
            data: {
                id: c.id, label: c.name,
                color: other.community_color || '#888',
                size: 10 + c.weight * 30,
            }
        });
        elements.push({
            group: 'edges',
            data: {
                source: centerNode.id, target: c.id,
                weight: c.weight,
            }
        });
    });

    // Edges between connected nodes
    const allEdges = DATA.edges['0.15'] || DATA.edges['0.2'] || [];
    allEdges.forEach(e => {
        if (connIds.has(e.source) && connIds.has(e.target) && e.source !== centerNode.id && e.target !== centerNode.id) {
            elements.push({
                group: 'edges',
                data: { source: e.source, target: e.target, weight: e.weight }
            });
        }
    });

    egoCy = cytoscape({
        container: document.getElementById('ego-cy'),
        elements: elements,
        style: [
            {
                selector: 'node',
                style: {
                    'background-color': 'data(color)',
                    'label': 'data(label)',
                    'width': 'data(size)', 'height': 'data(size)',
                    'font-size': 10, 'color': '#ddd',
                    'text-valign': 'bottom', 'text-margin-y': 5,
                    'text-outline-width': 2, 'text-outline-color': '#12121a',
                    'border-width': 2, 'border-color': 'rgba(255,255,255,0.5)',
                }
            },
            {
                selector: 'edge',
                style: {
                    'width': 'mapData(weight, 0, 1, 0.8, 5)',
                    'line-color': 'rgba(100,180,255,0.25)',
                    'curve-style': 'haystack',
                }
            }
        ],
        layout: {
            name: 'cose',
            animate: false,
            nodeRepulsion: 100000,
            idealEdgeLength: 100,
            gravity: 0.5,
        },
        wheelSensitivity: 0.3,
    });
    // Cytoscape needs a resize after container becomes visible in the DOM
    requestAnimationFrame(() => {
        setTimeout(() => {
            egoCy.resize();
            egoCy.layout({
                name: 'cose',
                animate: false,
                nodeRepulsion: 100000,
                idealEdgeLength: 100,
                gravity: 0.5,
            }).run();
            egoCy.fit(undefined, 20);
        }, 100);
    });
}

// ---- Init ----
async function init() {
    setupNav();
    await loadData();

    renderOverview();
    renderCommunities();
    renderRankings();
    setupExplorer();

    document.getElementById('loading-screen').classList.add('hidden');
}

init();
