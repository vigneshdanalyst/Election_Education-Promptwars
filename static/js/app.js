const API_BASE = '/api';

if (typeof Chart !== 'undefined') {
    Chart.defaults.color = '#8b949e';
    Chart.defaults.borderColor = '#30363d';
    Chart.defaults.font.family = "'IBM Plex Sans', sans-serif";
}

const routes = {
    '': '/static/pages/home.html',
    '#home': '/static/pages/home.html',
    '#candidates': '/static/pages/candidates.html',
    '#constituencies': '/static/pages/constituencies.html',
    '#elector-stats': '/static/pages/elector-stats.html',
    '#results': '/static/pages/results.html',
    '#chat': '/static/pages/chat.html',
    '#candidate': '/static/pages/candidate-detail.html'
};

let currentConstituencyData = [];

async function navigate() {
    let hash = window.location.hash;
    if (!routes[hash]) hash = '#home';

    document.querySelectorAll('.nav-links a').forEach(el => {
        el.classList.remove('active');
        if (el.getAttribute('href') === hash) el.classList.add('active');
    });

    const root = document.getElementById('app-root');
    root.innerHTML = '<div class="skeleton" style="height: 400px; width: 100%;"></div>';

    try {
        const response = await fetch(routes[hash]);
        if (!response.ok) throw new Error("Page not found");
        const html = await response.text();
        root.innerHTML = html;

        const state = document.getElementById('global-state-filter')?.value || '';
        const constId = document.getElementById('global-constituency-filter')?.value || '';

        if (hash === '#home' || hash === '') initHome(state, constId);
        if (hash === '#candidates') initCandidates(state, constId);
        if (hash === '#constituencies') initConstituencies(state, constId);
        if (hash === '#results') initResults();
        if (hash === '#chat') initChat();
        if (hash === '#elector-stats') initElectorStats(state);
        if (hash.startsWith('#candidate/')) initCandidateDetail(hash.split('/')[1]);

    } catch (e) {
        root.innerHTML = `<div class="card"><h2 class="text-saffron">Error</h2><p>Could not load page. ${e.message}</p></div>`;
    }
}

window.addEventListener('hashchange', navigate);
window.addEventListener('DOMContentLoaded', async () => {
    await loadCountdownDate();
    navigate();
    startCountdown();
    initGlobalFilters();
});

async function initGlobalFilters() {
    const stateFilter = document.getElementById('global-state-filter');
    const constFilter = document.getElementById('global-constituency-filter');

    try {
        const res = await fetch(`${API_BASE}/states`);
        const states = await res.json();
        stateFilter.innerHTML = `<option value="">All India (5 States)</option>` +
            states.map(s => `<option value="${s}">${s}</option>`).join('');
    } catch(e) { console.error(e); }

    window.app = {
        onGlobalFilterChange: async (event) => {
            const state = stateFilter.value;
            let constId = constFilter.value;
            candidatePage = 1;

            if (event && event.target.id === 'global-state-filter') {
                await updateGlobalConstDropdown(state);
                constFilter.value = '';
                constId = '';
            }

            if (event && event.target.id === 'global-constituency-filter') {
                constId = constFilter.value;
            }

            const hash = window.location.hash || '#home';
            if (hash === '#home' || hash === '') initHome(state, constId);
            if (hash === '#candidates') initCandidates(state, constId);
            if (hash === '#constituencies') initConstituencies(state, constId);
            if (hash === '#elector-stats') initElectorStats(state);
            if (hash === '#results') initResults(state, constId);
        }
    };
}

async function updateGlobalConstDropdown(state) {
    const constFilter = document.getElementById('global-constituency-filter');
    if (!state) {
        constFilter.innerHTML = `<option value="" style="background:var(--bg-primary); color:white;">All Constituencies</option>`;
        return;
    }
    try {
        const res = await fetch(`${API_BASE}/constituencies?state=${encodeURIComponent(state)}`);
        const data = await res.json();
        constFilter.innerHTML = `<option value="" style="background:var(--bg-primary); color:white;">All Constituencies</option>` +
            data.map(c => `<option value="${c.id}" style="background:var(--bg-primary); color:white;">${c.name}</option>`).join('');
    } catch(e) { console.error(e); }
}

function selectConstituency(id) {
    const stateFilter = document.getElementById('global-state-filter');
    const constFilter = document.getElementById('global-constituency-filter');
    const state = stateFilter?.value || '';
    constFilter.value = id;
    window.app.onGlobalFilterChange({ target: { id: 'global-constituency-filter' } });
}

let countdownInterval = null;
let countDateString = "May 4, 2026 08:00:00";

async function loadCountdownDate() {
    try {
        const res = await fetch(`${API_BASE}/config`);
        const cfg = await res.json();
        countDateString = cfg.counting_date || countDateString;
    } catch (e) {
        console.warn('Using default countdown date:', e);
    }
}

function startCountdown() {
    if (countdownInterval) clearInterval(countdownInterval);

    const tick = () => {
        const countdownEls = document.querySelectorAll('#countdown-timer');
        if (!countdownEls.length) return;
        const countDate = new Date(countDateString).getTime();
        const now = new Date().getTime();
        const gap = countDate - now;

        if (gap <= 0) {
            countdownEls.forEach(el => { el.innerText = 'Counting in progress!'; });
            return;
        }

        const d = Math.floor(gap / (1000 * 60 * 60 * 24));
        const h = Math.floor((gap % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const m = Math.floor((gap % (1000 * 60 * 60)) / (1000 * 60));
        const s = Math.floor((gap % (1000 * 60)) / 1000);

        countdownEls.forEach(el => {
            el.innerText = `${d}d ${h}h ${m}m ${s}s for Results`;
        });
    };
    tick();
    countdownInterval = setInterval(tick, 1000);
}

async function initHome(state = '', constId = '') {
    try {
        let url = `${API_BASE}/overview`;
        const params = new URLSearchParams();
        if (state) params.append('state', state);
        if (constId) params.append('constituency_id', constId);
        if (params.toString()) url += `?${params.toString()}`;

        const res = await fetch(url);
        const data = await res.json();

        const el = (id) => document.getElementById(id);
        if (el('stat-seats')) el('stat-seats').innerText = data.stats.seats.toLocaleString();
        if (el('stat-candidates')) el('stat-candidates').innerText = data.stats.candidates.toLocaleString();
        if (el('stat-electors')) el('stat-electors').innerText = (data.stats.electors || 0).toLocaleString();
        if (el('stat-polled')) el('stat-polled').innerText = (data.stats.polled || 0).toLocaleString();
        if (el('stat-turnout')) el('stat-turnout').innerText = data.stats.turnout + "%";

        const summaryBody = el('state-summary-tbody');
        if (summaryBody) {
            const rows = data.state_summaries || [];
            summaryBody.innerHTML = rows.length ? rows.map(row => `
                <tr>
                    <td><a href="${row.source_url}" target="_blank" rel="noopener">${row.state}</a></td>
                    <td>${row.seats.toLocaleString()}</td>
                    <td>${row.candidates.toLocaleString()}</td>
                    <td>${row.electors.toLocaleString()}</td>
                    <td>${row.polled.toLocaleString()}</td>
                    <td>${row.turnout.toFixed(2)}%</td>
                </tr>
            `).join('') : `<tr><td colspan="6" class="text-muted">Constituency-level database view selected.</td></tr>`;
        }
    } catch(e) {
        console.error("Failed to load home data", e);
    }
}

let candidatePage = 1;
const candidateLimit = 50;
let loadedCandidates = [];

function changeCandidatePage(delta) {
    candidatePage = Math.max(1, candidatePage + delta);
    initCandidates();
}

async function initCandidates(state = '', constId = '') {
    const stateFilter = document.getElementById('global-state-filter');
    const constFilter = document.getElementById('global-constituency-filter');
    const searchInput = document.getElementById('candidate-search');
    const reservedSelect = document.getElementById('candidate-reserved');

    if (searchInput && !searchInput.dataset.bound) {
        searchInput.addEventListener('input', applyCandidateFilters);
        searchInput.dataset.bound = '1';
    }
    if (reservedSelect && !reservedSelect.dataset.bound) {
        reservedSelect.addEventListener('change', () => {
            candidatePage = 1;
            initCandidates();
        });
        reservedSelect.dataset.bound = '1';
    }

    await fetchCandidatesData(state || stateFilter?.value || '', constId || constFilter?.value || '');
}

function applyCandidateFilters() {
    const search = (document.getElementById('candidate-search')?.value || '').toLowerCase().trim();
    const rows = loadedCandidates.filter(c => {
        if (!search) return true;
        const name = (c.name || '').toLowerCase();
        const constituency = (c.constituency_name || '').toLowerCase();
        const party = (c.party_abbr || c.party_name || '').toLowerCase();
        return name.includes(search) || constituency.includes(search) || party.includes(search);
    });

    const tbody = document.getElementById('candidates-tbody');
    if (tbody) {
        tbody.innerHTML = rows.length ? rows.map(c => `
            <tr>
                <td><img src="${c.photo_url}" width="40" style="border-radius:50%"></td>
                <td><a href="${c.myneta_url || `#candidate/${c.id}`}" ${c.myneta_url ? 'target="_blank" rel="noopener"' : ''} style="color:var(--accent-saffron); font-weight:bold;">${c.name}</a><br><small class="text-muted">${c.age ? c.age + ' Yrs' : ''} ${c.gender ? '• ' + c.gender : ''}</small></td>
                <td><span style="color:${c.party_color || '#9E9E9E'};font-weight:bold">${c.party_abbr || '-'}</span></td>
                <td>${c.constituency_name || '-'}<br><small class="text-muted">${c.state_name || ''}</small></td>
                <td>${c.education || '-'}</td>
                <td>Rs ${c.assets_cr || 0} Cr</td>
                <td>${c.criminal_cases > 0 ? `<span style="color:red">${c.criminal_cases}</span>` : '0'}</td>
            </tr>
        `).join('') : `<tr><td colspan="7" class="text-muted">No candidates match the search.</td></tr>`;
    }
}

async function fetchCandidatesData(state = '', constId = '') {
    const reserved = document.getElementById('candidate-reserved')?.value || '';
    const params = new URLSearchParams({ limit: String(candidateLimit), page: String(candidatePage) });
    if (state) params.append('state', state);
    if (constId) params.append('constituency_id', constId);
    if (reserved) params.append('reserved', reserved);

    const tbody = document.getElementById('candidates-tbody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="text-muted">Loading candidates...</td></tr>`;

    const res = await fetch(`${API_BASE}/candidates?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    const data = await res.json();
    loadedCandidates = data.data || [];
    const source = document.getElementById('candidate-source');
    if (source) source.innerText = `${data.source || 'Database'} | ${(data.total || loadedCandidates.length).toLocaleString()} candidates`;
    const totalPages = Math.max(1, Math.ceil((data.total || loadedCandidates.length || 1) / candidateLimit));
    const pageInfo = document.getElementById('candidate-page-info');
    const prev = document.getElementById('candidate-prev');
    const next = document.getElementById('candidate-next');
    if (pageInfo) pageInfo.innerText = `Page ${candidatePage.toLocaleString()} of ${totalPages.toLocaleString()}`;
    if (prev) prev.disabled = candidatePage <= 1;
    if (next) next.disabled = candidatePage >= totalPages;

    applyCandidateFilters();
}

async function initConstituencies(state = '', constId = '') {
    const selectedState = state || document.getElementById('global-state-filter')?.value || '';

    const map = L.map('map').setView([20.5937, 78.9629], selectedState ? 6 : 5);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        className: 'map-tiles'
    }).addTo(map);

    const style = document.createElement('style');
    style.innerHTML = `.map-tiles { filter: brightness(0.6) invert(1) contrast(3) hue-rotate(200deg) saturate(0.3) brightness(0.7); }`;
    document.head.appendChild(style);

    const params = new URLSearchParams();
    if (selectedState) params.append('state', selectedState);
    const data = await fetch(`${API_BASE}/constituencies?${params.toString()}`).then(r => r.json());
    currentConstituencyData = data;

    const list = document.getElementById('constituencies-list');
    const search = document.getElementById('constituency-search');
    const activeConstId = constId || document.getElementById('global-constituency-filter')?.value || '';

    const renderList = (items) => {
        list.innerHTML = items.map(c => {
            const isActive = String(c.id) === String(activeConstId);
            return `
                <div class="card mb-2" style="padding: 10px; cursor: pointer; border-left: 4px solid ${isActive ? 'var(--accent-saffron)' : 'transparent'}; background: ${isActive ? 'var(--bg-secondary)' : 'var(--bg-card)'};" onclick="selectConstituency('${c.id}')">
                    <strong>${c.name}</strong> (${c.type || 'GEN'})<br>
                    <small class="text-muted">${c.state} | ${c.source || 'MyNeta'}</small>
                    <br><button class="btn btn-primary mt-1" style="font-size:0.8em; padding:4px 10px;" onclick="event.stopPropagation(); selectConstituency('${c.id}')">Select</button>
                </div>
            `;
        }).join('');
    };

    renderList(data);

    data.forEach(c => {
        if (c.lat && c.lng) {
            const isActive = String(c.id) === String(activeConstId);
            L.marker([c.lat, c.lng]).addTo(map).bindPopup(`
                <strong>${c.name}</strong><br>
                ${c.state} (${c.type || 'GEN'})<br>
                <button onclick="selectConstituency('${c.id}')" style="margin-top:4px; padding:4px 8px; cursor:pointer;">Select</button>
            `);
        }
    });

    if (data.length && data.some(c => c.lat && c.lng)) {
        const bounds = L.latLngBounds(data.filter(c => c.lat && c.lng).map(c => [c.lat, c.lng]));
        map.fitBounds(bounds.pad(0.25));
    }

    if (search) {
        search.oninput = () => {
            const q = search.value.toLowerCase();
            renderList(data.filter(c => c.name.toLowerCase().includes(q) || c.state.toLowerCase().includes(q)));
        };
    }
}

async function initResults(state = '', constId = '') {
    startCountdown();
    const overview = await fetch(`${API_BASE}/overview`).then(r => r.json());
    const stateBody = document.getElementById('results-state-tbody');
    if (stateBody) {
        stateBody.innerHTML = overview.state_summaries.map(row => `
            <div class="card stat-card">
                <div class="label">${row.state}</div>
                <div class="value">${row.seats.toLocaleString()}</div>
                <small class="text-muted">seats awaiting counting</small>
            </div>
        `).join('');
    }

    try {
        const res = await fetch(`${API_BASE}/results/live`);
        const data = await res.json();
        const tbody = document.getElementById('results-tbody');
        if (tbody) {
            tbody.innerHTML = data.length ? data.map(r => `
                <tr>
                    <td>${r.const_name}</td>
                    <td>${r.winner_name}</td>
                    <td style="color:${r.winner_color}; font-weight:bold">${r.winner_party}</td>
                    <td>${(r.votes || 0).toLocaleString()}</td>
                    <td>${(r.margin || 0).toLocaleString()}</td>
                    <td><span style="color: ${r.status === 'Won' ? 'var(--accent-green)' : 'var(--accent-saffron)'}">${r.status}</span></td>
                </tr>
            `).join('') : `<tr><td colspan="6" class="text-muted">No live results available yet.</td></tr>`;
        }
    } catch (e) {
        console.error('Failed to load live results:', e);
        const tbody = document.getElementById('results-tbody');
        if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="text-muted">Failed to load live results.</td></tr>`;
    }
}

let chatHistory = [];
async function initChat() {
    document.getElementById('chat-input-box').addEventListener('keypress', function (e) {
        if (e.key === 'Enter') sendChatMessage();
    });
}

async function sendChatMessage() {
    const input = document.getElementById('chat-input-box');
    const msg = input.value.trim();
    if(!msg) return;

    appendMessage('user', msg);
    input.value = '';

    try {
        const res = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msg, history: chatHistory, language: 'english' })
        });
        const data = await res.json();
        appendMessage('ai', data.response + `<br><br><small class="text-muted">Sources: ${data.sources.join(', ')}</small>`);
        chatHistory.push({ role: 'user', content: msg });
        chatHistory.push({ role: 'assistant', content: data.response });
    } catch (e) {
        appendMessage('ai', 'Connection error.');
    }
}

function appendMessage(role, html) {
    const container = document.getElementById('chat-messages');
    container.innerHTML += `<div class="msg ${role}">${html}</div>`;
    container.scrollTop = container.scrollHeight;
}

async function initElectorStats(state = '') {
    try {
        let url = `${API_BASE}/elector-stats`;
        if (state) url += `?state=${encodeURIComponent(state)}`;
        const data = await fetch(url).then(r => r.json());
        const el = (id) => document.getElementById(id);
        if (el('e-total')) el('e-total').innerText = data.summary.total.toLocaleString();
        if (el('e-polled')) el('e-polled').innerText = data.summary.polled.toLocaleString();
        if (el('e-states')) el('e-states').innerText = data.state_summaries.length;
        const overallTurnout = ((data.summary.polled / data.summary.total) * 100).toFixed(2);
        if (el('e-turnout')) el('e-turnout').innerText = `${overallTurnout}%`;

        const turnoutDiv = el('turnout-2026');
        if (turnoutDiv) {
            turnoutDiv.innerHTML = data.state_summaries.map(row => `
                <div style="text-align:center; padding:10px;">
                    <strong style="color:var(--accent-blue); font-size:1.1em">${row.state}</strong><br>
                    <span style="font-size:1.5em; font-weight:bold; color:var(--text-primary)">${row.turnout.toFixed(2)}%</span>
                </div>
            `).join('');
        }

        const electorTbody = el('elector-state-tbody');
        if (electorTbody) {
            electorTbody.innerHTML = data.state_summaries.map(row => `
                <tr>
                    <td>${row.state}</td>
                    <td>${row.electors.toLocaleString()}</td>
                    <td>${row.polled.toLocaleString()}</td>
                    <td>${row.turnout.toFixed(2)}%</td>
                </tr>
            `).join('');
        }

        const canvas = el('ageChart');
        if (canvas) {
            const oldChart = Chart.getChart(canvas);
            if (oldChart) oldChart.destroy();
            new Chart(canvas.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: data.state_summaries.map(row => row.state),
                    datasets: [{ label: 'Turnout %', data: data.state_summaries.map(row => row.turnout), backgroundColor: '#58a6ff' }]
                },
                options: { scales: { y: { beginAtZero: true, max: 100 } } }
            });
        }
    } catch(e) { console.error(e); }
}

async function searchVoter() {
    const epic = document.getElementById('epic-input').value;
    if(!epic) return;
    try {
        const res = await fetch(`${API_BASE}/voter?epic=${epic}`);
        const data = await res.json();
        const div = document.getElementById('voter-result');
        div.style.display = 'block';
        if(data.detail) { div.innerHTML = data.detail; return; }
        div.innerHTML = `<strong>Name:</strong> ${data.name} <br> <strong>Booth:</strong> ${data.booth} <br> <strong>Const:</strong> ${data.constituency}`;
    } catch(e) { console.error(e); }
}

async function initStats(state = '', constId = '') {
    try {
        const params = new URLSearchParams();
        const selectedState = state || document.getElementById('global-state-filter')?.value || '';
        if (selectedState) params.append('state', selectedState);
        if (constId) params.append('constituency_id', constId);
        const data = await fetch(`${API_BASE}/stats/advanced?${params.toString()}`).then(r => r.json());

        const el = (id) => document.getElementById(id);
        if (el('stat-crorepatis')) el('stat-crorepatis').innerText = data.crorepatis.count;
        if (el('stat-crorepatis-pct')) el('stat-crorepatis-pct').innerText = `${data.crorepatis.percentage}% of live sample`;
        if (el('stat-criminals')) el('stat-criminals').innerText = data.criminal_cases.count;
        if (el('stat-criminals-pct')) el('stat-criminals-pct').innerText = `${data.criminal_cases.percentage}% of live sample`;
        const source = el('advanced-source');
        if (source) source.innerText = `${data.source || 'Database'} | sample size: ${data.sample_size || 'local'}`;

        ['eduChart', 'genderChart'].forEach(id => {
            const chart = Chart.getChart(id);
            if (chart) chart.destroy();
        });

        const eduCanvas = el('eduChart');
        if (eduCanvas) {
            new Chart(eduCanvas.getContext('2d'), {
                type: 'pie',
                data: { labels: Object.keys(data.education), datasets: [{ data: Object.values(data.education), backgroundColor: ['#FF9933', '#138808', '#58a6ff', '#e6edf3', '#8b949e', '#D32F2F'] }] }
            });
        }

        const genderCanvas = el('genderChart');
        if (genderCanvas) {
            new Chart(genderCanvas.getContext('2d'), {
                type: 'bar',
                data: { labels: Object.keys(data.gender_ratio), datasets: [{ label: 'Candidates', data: Object.values(data.gender_ratio), backgroundColor: '#FF9933' }] }
            });
        }
    } catch(e) { console.error(e); }
}

async function initCandidateDetail(id) {
    try {
        const res = await fetch(`${API_BASE}/candidate/${id}`);
        const c = await res.json();

        const el = (id) => document.getElementById(id);
        if (el('c-photo')) el('c-photo').src = c.photo_url;
        if (el('c-name')) el('c-name').innerText = c.name;
        if (el('c-party')) {
            el('c-party').innerText = c.party_name || c.party_abbr;
            el('c-party').style.backgroundColor = c.party_color;
        }
        if (el('c-constituency')) el('c-constituency').innerText = `${c.constituency_name || ''}, ${c.state_name || ''}`;
        if (el('c-age')) el('c-age').innerText = c.age || '--';
        if (el('c-gender')) el('c-gender').innerText = c.gender || '--';
        if (el('c-edu')) el('c-edu').innerText = c.education || '--';
        if (el('c-prof')) el('c-prof').innerText = c.profession || 'N/A';
        if (el('c-pan')) el('c-pan').innerText = c.pan_status || 'N/A';

        const criminal = el('c-criminal-summary');
        if (criminal) {
            criminal.innerText = c.criminal_cases > 0 ? `${c.criminal_cases} Case(s)` : 'Clean Record';
            criminal.style.color = c.criminal_cases > 0 ? 'var(--accent-red)' : 'var(--accent-green)';
        }

        if (el('c-assets-total')) el('c-assets-total').innerText = `Rs ${c.assets_cr || 0} Cr`;
        if (el('c-assets-movable')) el('c-assets-movable').innerText = `Rs ${c.movable_assets || 0} Cr`;
        if (el('c-assets-immovable')) el('c-assets-immovable').innerText = `Rs ${c.immovable_assets || 0} Cr`;
        if (el('c-liabilities')) el('c-liabilities').innerText = `Rs ${c.liabilities || 0} Cr`;

        const canvas = el('assetChart');
        if (canvas) {
            const ctx = canvas.getContext('2d');
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: ['Movable', 'Immovable', 'Liabilities'],
                    datasets: [{
                        label: 'Amount in Crores',
                        data: [c.movable_assets || 0, c.immovable_assets || 0, c.liabilities || 0],
                        backgroundColor: ['#58a6ff', '#138808', '#d32f2f']
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: { beginAtZero: true, grid: { color: '#30363d' } }
                    }
                }
            });
        }
    } catch(e) { console.error("Error loading candidate details", e); }
}
