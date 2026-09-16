let currentSessionId = null;
let isGenerating = false;
let currentTab = 'playground';
let thinkingDisplayMode = 'hidden';
let attachedFiles = [];

document.addEventListener('DOMContentLoaded', async () => {
    const ready = await initApp();
    if (!ready) return;

    const baseV1 = window.location.origin + '/v1';
    const baseAnthropic = window.location.origin + '/anthropic/v1';

    const setContent = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    };
    setContent('api-base-url', baseV1);
    setContent('api-base-url-keys', baseV1);
    setContent('api-anthropic-url-keys', baseAnthropic);

    setupToggleChips();
    setupKeyboardShortcuts();
    setupFileDropAndPaste();

    await Promise.all([
        fetchPoolStatus(),
        fetchApiKeys(),
        fetchSkills()
    ]);

    setInterval(fetchPoolStatus, 10000);
});

function setupToggleChips() {
    document.querySelectorAll('.toggle-chip').forEach(chip => {
        const input = chip.querySelector('input[type="checkbox"]');
        if (!input) return;
        updateChipState(chip, input);
        input.addEventListener('change', () => updateChipState(chip, input));
    });
}

function updateChipState(chip, input) {
    const activeClass = chip.dataset.activeClass;
    if (input.checked) {
        chip.classList.add(activeClass);
    } else {
        chip.classList.remove(activeClass);
        ['active-purple', 'active-sky', 'active-amber'].forEach(c => {
            if (c !== activeClass) chip.classList.remove(c);
        });
    }
}

function setupKeyboardShortcuts() {
    const textarea = document.getElementById('prompt-input');
    if (!textarea) return;
    textarea.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
}

function switchTab(tab) {
    currentTab = tab;
    ['playground', 'pool', 'keys', 'skills', 'docs', 'settings'].forEach(t => {
        const view = document.getElementById(`view-${t}`);
        const btn = document.getElementById(`tab-${t}`);
        if (!view || !btn) return;
        if (t === tab) {
            view.classList.remove('hidden');
            btn.classList.add('active');
        } else {
            view.classList.add('hidden');
            btn.classList.remove('active');
        }
    });

    if (tab === 'pool') fetchPoolStatus();
    if (tab === 'keys') fetchApiKeys();
    if (tab === 'skills') fetchSkills();
}

function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<i class="fa-solid ${type === 'success' ? 'fa-circle-check' : 'fa-circle-xmark'}"></i> ${message}`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

async function copyToClipboard(text, msg = 'Berhasil disalin ke clipboard!') {
    if (!text) {
        showToast('Tidak ada teks untuk disalin', 'error');
        return;
    }
    try {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(text);
        } else {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            ta.style.top = '-9999px';
            ta.setAttribute('readonly', '');
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
        }
        showToast(msg);
    } catch (e) {
        console.error('Copy failed:', e);
        showToast('Gagal menyalin: ' + e.message, 'error');
    }
}
window.copyToClipboard = copyToClipboard;

function toggleTokenMask(index, fullToken, maskedName) {
    const span = document.getElementById(`token-disp-${index}`);
    const btn = document.getElementById(`btn-toggle-mask-${index}`);
    if (!span || !btn) return;
    const isRevealed = span.dataset.revealed === 'true';
    if (isRevealed) {
        span.textContent = maskedName;
        span.dataset.revealed = 'false';
        btn.innerHTML = '<i class="fa-regular fa-eye"></i>';
        btn.title = 'Lihat Token Utuh';
    } else {
        span.textContent = fullToken;
        span.dataset.revealed = 'true';
        btn.innerHTML = '<i class="fa-regular fa-eye-slash"></i>';
        btn.title = 'Sembunyikan Token';
    }
}
window.toggleTokenMask = toggleTokenMask;

function escapeHtml(str) {
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function cleanRenderMarkdown(raw) {
    if (!raw) return '';
    let html = '';
    if (typeof marked !== 'undefined' && marked.parse) {
        try { html = marked.parse(raw); } catch { html = ''; }
    }
    if (!html || html.includes('**')) {
        let text = escapeHtml(raw);
        text = text.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
        text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
        text = text.replace(/^### (.*$)/gim, '<h3>$1</h3>');
        text = text.replace(/^## (.*$)/gim, '<h2>$1</h2>');
        text = text.replace(/^# (.*$)/gim, '<h1>$1</h1>');
        text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        text = text.replace(/__(.*?)__/g, '<strong>$1</strong>');
        text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
        text = text.replace(/^\s*[-*]\s+(.*$)/gim, '<li class="ml-4 list-disc">$1</li>');
        text = text.replace(/^\s*(\d+)\.\s+(.*$)/gim, '<li class="ml-4 list-decimal">$2</li>');
        text = text.replace(/\n\n/g, '<div class="h-2"></div>');
        text = text.replace(/\n/g, '<br/>');
        html = text;
    }
    html = html.replace(/\[citation:(\d+)\]/g, '<span class="citation-badge">🔍 [$1]</span>');
    return html;
}

async function fetchPoolStatus() {
    try {
        const res = await authFetch('/api/status');
        if (!res.ok) return;
        const data = await res.json();

        const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };

        setEl('stat-total', data.total_tokens || 0);
        setEl('badge-total', data.total_tokens || 0);
        setEl('stat-healthy', data.healthy || 0);
        setEl('stat-cooldown', data.cooldown || 0);
        setEl('stat-strategy', data.strategy || 'round_robin');
        setVal('setting-strategy', data.strategy || 'round_robin');
        setVal('setting-boost', String(data.boost_enabled));

        if (data.thinking_display) {
            thinkingDisplayMode = data.thinking_display;
            setVal('setting-thinking-display', data.thinking_display);
        }

        const boostPill = document.getElementById('boost-pill');
        if (boostPill) {
            boostPill.style.display = data.boost_enabled ? 'flex' : 'none';
        }
        setEl('hdr-healthy', `${data.healthy || 0}/${data.total_tokens || 0}`);

        let totalLat = 0, countLat = 0;
        (data.tokens || []).forEach(t => {
            if (t.latency_ms > 0) { totalLat += t.latency_ms; countLat++; }
        });
        setEl('stat-latency', countLat > 0 ? `${(totalLat / countLat).toFixed(0)} ms` : '—');

        renderTokensTable(data.tokens || []);

        const accountSelect = document.getElementById('chat-account');
        if (accountSelect) {
            const currentVal = accountSelect.value;
            let options = '<option value="auto">Otomatis (Pool)</option>';
            (data.tokens || []).forEach((t, idx) => {
                const label = `Akun #${idx + 1} (${t.name || t.token_masked || 'Token'})`;
                const isHealthy = t.status === 'healthy';
                const statusSuffix = isHealthy ? '' : ` [${t.status}]`;
                const optVal = t.name || t.token_masked;
                options += `<option value="${escapeHtml(optVal)}"${optVal === currentVal ? ' selected' : ''}>${escapeHtml(label + statusSuffix)}</option>`;
            });
            accountSelect.innerHTML = options;
        }
    } catch {}
}

function renderTokensTable(tokens) {
    const tbody = document.getElementById('tokens-tbody');
    if (!tbody) return;
    if (tokens.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Belum ada akun di database pool</td></tr>';
        return;
    }
    tbody.innerHTML = tokens.map((t, i) => {
        let badge = '';
        if (t.status === 'healthy') {
            badge = '<span class="status-badge badge-healthy"><i class="fa-solid fa-circle-check"></i> Aktif</span>';
        } else if (t.status === 'cooldown') {
            const rem = t.cooldown_remaining ? t.cooldown_remaining.toFixed(0) : 0;
            badge = `<span class="status-badge badge-cooldown"><i class="fa-solid fa-clock"></i> Cooldown ${rem}s</span>`;
        } else {
            badge = '<span class="status-badge badge-invalid"><i class="fa-solid fa-triangle-exclamation"></i> Invalid</span>';
        }

        const lat = t.latency_ms > 0 ? `<span class="color-purple" style="font-weight:600">${t.latency_ms.toFixed(0)} ms</span>` : '<span style="color:var(--text-muted)">—</span>';
        const reqs = `${t.total_successes || 0} / ${(t.total_successes || 0) + (t.total_errors || 0)}`;
        const err = t.last_error ? `<span class="color-rose" title="${escapeHtml(t.last_error)}" style="cursor:help;font-size:11px">${escapeHtml(t.last_error.slice(0, 28))}${t.last_error.length > 28 ? '…' : ''}</span>` : '<span style="color:var(--text-muted)">—</span>';
        const rawToken = t.token || t.name;
        const displayName = t.token_masked || t.name;

        return `<tr id="token-row-${i}">
            <td style="color:var(--text-muted)">${i + 1}</td>
            <td>
                <div style="display:flex;align-items:center;gap:6px">
                    <span id="token-disp-${i}" data-revealed="false" style="color:var(--text-primary);font-weight:600;font-family:'JetBrains Mono',monospace;font-size:11.5px;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(displayName)}</span>
                    <button onclick="copyToClipboard('${escapeHtml(rawToken)}', 'Token akun berhasil disalin!')" class="btn-icon" style="width:20px;height:20px;font-size:10px" title="Salin Token Akun">
                        <i class="fa-regular fa-copy"></i>
                    </button>
                    <button onclick="toggleTokenMask(${i}, '${escapeHtml(rawToken)}', '${escapeHtml(displayName)}')" id="btn-toggle-mask-${i}" class="btn-icon" style="width:20px;height:20px;font-size:10px" title="Lihat / Sembunyikan Token">
                        <i class="fa-regular fa-eye"></i>
                    </button>
                </div>
            </td>
            <td>${badge}</td>
            <td>${lat}</td>
            <td style="font-size:11.5px">${reqs}</td>
            <td>${err}</td>
            <td style="text-align:right">
                <div style="display:inline-flex;align-items:center;gap:6px">
                    <button id="btn-test-token-${i}" onclick="testSingleToken('${escapeHtml(rawToken)}', ${i})" class="btn-secondary btn-sm" title="Test Token Langsung">
                        <i class="fa-solid fa-bolt" style="color:var(--accent-amber)"></i> Test
                    </button>
                    <button onclick="removeToken('${escapeHtml(t.name)}')" class="btn-danger-ghost btn-sm" title="Hapus dari Pool">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </td>
        </tr>`;
    }).join('');
}

async function testSingleToken(token, rowIndex) {
    const btn = document.getElementById(`btn-test-token-${rowIndex}`);
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner spin"></i> Menguji...';
    }
    try {
        const res = await authFetch('/api/tokens/test', {
            method: 'POST',
            body: JSON.stringify({ token })
        });
        const data = await res.json();
        if (data.valid) {
            showToast(`✅ Akun valid! Latensi: ${data.latency_ms} ms`);
        } else {
            showToast(`❌ Akun gagal: ${data.error || 'Autentikasi ditolak'}`, 'error');
        }
        await fetchPoolStatus();
    } catch (e) {
        showToast('Gagal menguji token: ' + e.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-bolt" style="color:var(--accent-amber)"></i> Test';
        }
    }
}

async function testAllTokens() {
    const btn = document.getElementById('btn-test-all');
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner spin"></i> Menguji Semua...';
    try {
        const res = await authFetch('/api/tokens/test-all', { method: 'POST' });
        const data = await res.json();
        const results = data.results || {};
        let validCount = 0;
        let totalCount = 0;
        for (const k in results) {
            totalCount++;
            if (results[k]) validCount++;
        }
        showToast(`Uji selesai: ${validCount}/${totalCount} akun aktif & sehat!`);
        await fetchPoolStatus();
    } catch (e) {
        showToast('Gagal menguji semua token: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-bolt"></i> Test Semua';
    }
}

async function triggerLearn() {
    const btn = document.getElementById('btn-learn');
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner spin"></i> Harvesting...';
    try {
        const res = await authFetch('/api/learn', { method: 'POST' });
        const result = await res.json();
        showToast(`/learn selesai: +${result.added_to_pool || 0} akun ditambahkan, total ${result.healthy_count || 0} sehat.`);
        await fetchPoolStatus();
    } catch (e) {
        showToast('Gagal /learn: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-brain"></i> /learn';
    }
}

function openModalAddToken() {
    document.getElementById('modal-add-token').classList.remove('hidden');
    document.getElementById('input-new-tokens').focus();
}

function closeModalAddToken() {
    document.getElementById('modal-add-token').classList.add('hidden');
    document.getElementById('input-new-tokens').value = '';
}

async function submitNewTokens() {
    const raw = document.getElementById('input-new-tokens').value.trim();
    if (!raw) return;
    const saveDisk = document.getElementById('check-save-disk').checked;
    const btn = document.getElementById('btn-submit-tokens');
    btn.disabled = true;
    btn.textContent = 'Menyimpan...';
    try {
        const res = await authFetch('/api/tokens/add', {
            method: 'POST',
            body: JSON.stringify({ tokens_raw: raw, save_disk: saveDisk })
        });
        const data = await res.json();
        showToast(`+${data.added} token disimpan ke database`);
        closeModalAddToken();
        await fetchPoolStatus();
    } catch (e) {
        showToast('Gagal: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Tambah';
    }
}

async function removeToken(tokenName) {
    if (!confirm(`Hapus akun "${tokenName}" dari database pool?`)) return;
    try {
        await authFetch('/api/tokens/remove', {
            method: 'POST',
            body: JSON.stringify({ token: tokenName })
        });
        showToast('Token dihapus');
        await fetchPoolStatus();
    } catch (e) {
        showToast('Gagal menghapus', 'error');
    }
}

async function saveSettings() {
    const strategy = document.getElementById('setting-strategy').value;
    const boost = document.getElementById('setting-boost').value === 'true';
    const thinkingDisp = document.getElementById('setting-thinking-display').value;

    try {
        const res = await authFetch('/api/settings', {
            method: 'POST',
            body: JSON.stringify({
                strategy,
                boost_enabled: boost,
                thinking_display: thinkingDisp
            })
        });
        if (res.ok) {
            thinkingDisplayMode = thinkingDisp;
            showToast('Pengaturan berhasil disimpan');
            await fetchPoolStatus();
        }
    } catch (e) {
        showToast('Gagal menyimpan', 'error');
    }
}

// ==========================================================================
// API Keys Generator & Management
// ==========================================================================
async function fetchApiKeys() {
    try {
        const res = await authFetch('/api/keys');
        if (!res.ok) return;
        const data = await res.json();
        const keys = data.keys || [];
        const badge = document.getElementById('badge-keys');
        if (badge) {
            badge.textContent = keys.length;
            badge.style.display = keys.length > 0 ? 'inline-block' : 'none';
        }
        renderApiKeysTable(keys);
    } catch {}
}

function renderApiKeysTable(keys) {
    const tbody = document.getElementById('keys-tbody');
    if (!tbody) return;
    if (keys.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Belum ada Kunci API yang dibuat. Klik "Generate Kunci Baru" di atas.</td></tr>';
        return;
    }
    tbody.innerHTML = keys.map((k) => {
        const created = k.created_at ? k.created_at.slice(0, 10) : '—';
        const lastUsed = k.last_used ? k.last_used.replace('T', ' ').slice(0, 16) : 'Belum pernah';
        const checked = k.active ? 'checked' : '';

        return `<tr>
            <td style="color:var(--text-primary);font-weight:600">${escapeHtml(k.name)}</td>
            <td>
                <div style="display:flex;align-items:center;gap:6px">
                    <code style="color:var(--accent-sky);font-size:11.5px">${escapeHtml(k.key_masked)}</code>
                    <button onclick="copyToClipboard('${escapeHtml(k.key)}')" class="btn-icon" style="width:20px;height:20px;font-size:10px" title="Salin Kunci">
                        <i class="fa-regular fa-copy"></i>
                    </button>
                </div>
            </td>
            <td style="color:var(--text-muted);font-size:11px">${created}</td>
            <td style="font-weight:600">${k.requests_count || 0}</td>
            <td style="color:var(--text-muted);font-size:11px">${lastUsed}</td>
            <td>
                <label class="switch">
                    <input type="checkbox" ${checked} onchange="toggleApiKey('${k.id}', this.checked)">
                    <span class="slider"></span>
                </label>
            </td>
            <td style="text-align:right">
                <button onclick="revokeApiKey('${k.id}', '${escapeHtml(k.name)}')" class="btn-danger-ghost btn-sm" title="Revoke Kunci">
                    <i class="fa-solid fa-trash-can"></i> Revoke
                </button>
            </td>
        </tr>`;
    }).join('');
}

function openModalGenerateKey() {
    document.getElementById('modal-generate-key').classList.remove('hidden');
    document.getElementById('input-key-name').focus();
}

function closeModalGenerateKey() {
    document.getElementById('modal-generate-key').classList.add('hidden');
}

function closeModalKeyResult() {
    document.getElementById('modal-key-result').classList.add('hidden');
}

async function submitGenerateKey() {
    const name = document.getElementById('input-key-name').value.trim();
    const btn = document.getElementById('btn-submit-generate-key');
    btn.disabled = true;
    btn.textContent = 'Membuat...';
    try {
        const res = await authFetch('/api/keys/generate', {
            method: 'POST',
            body: JSON.stringify({ name: name || 'Cursor IDE' })
        });
        const data = await res.json();
        closeModalGenerateKey();

        document.getElementById('text-new-key-value').textContent = data.key.key;
        document.getElementById('modal-key-result').classList.remove('hidden');
        showToast('Kunci API baru berhasil dibuat!');
        await fetchApiKeys();
    } catch (e) {
        showToast('Gagal generate kunci: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Generate Kunci';
    }
}

async function revokeApiKey(keyId, name) {
    if (!confirm(`Hapus / Revoke Kunci API "${name}"? Klien yang menggunakannya tidak akan bisa mengakses API lagi.`)) return;
    try {
        await authFetch(`/api/keys/${keyId}`, { method: 'DELETE' });
        showToast('Kunci API telah direvoke');
        await fetchApiKeys();
    } catch (e) {
        showToast('Gagal revoke: ' + e.message, 'error');
    }
}

async function toggleApiKey(keyId, active) {
    try {
        await authFetch(`/api/keys/${keyId}/toggle`, {
            method: 'POST',
            body: JSON.stringify({ active })
        });
        showToast(active ? 'Kunci diaktifkan' : 'Kunci dinonaktifkan');
    } catch (e) {
        showToast('Gagal mengubah status kunci', 'error');
    }
}

// ==========================================================================
// Skills & AI Personas Manager
// ==========================================================================
let allLoadedSkills = [];

async function fetchSkills() {
    try {
        const res = await authFetch('/api/skills');
        if (!res.ok) return;
        const data = await res.json();
        allLoadedSkills = data.skills || [];
        const badge = document.getElementById('badge-skills');
        if (badge) {
            badge.textContent = allLoadedSkills.filter(s => s.is_active).length;
            badge.style.display = 'inline-block';
        }
        renderSkillsGrid(allLoadedSkills);
    } catch {}
}

function renderSkillsGrid(skills) {
    const grid = document.getElementById('skills-grid');
    if (!grid) return;
    if (skills.length === 0) {
        grid.innerHTML = '<div class="empty-state">Belum ada skill yang terpasang.</div>';
        return;
    }

    grid.innerHTML = skills.map(s => {
        const isBuiltin = s.is_builtin;
        const badgeClass = isBuiltin ? 'badge-builtin' : 'badge-custom';
        const badgeLabel = isBuiltin ? 'Bawaan' : 'Kustom';
        const activeClass = s.is_active ? 'active' : '';
        const checked = s.is_active ? 'checked' : '';

        let iconHtml = '<i class="fa-solid fa-wand-magic-sparkles"></i>';
        if (s.icon && s.icon.includes('fa-')) {
            iconHtml = `<i class="${escapeHtml(s.icon)}"></i>`;
        } else if (s.icon) {
            iconHtml = `<span>${escapeHtml(s.icon)}</span>`;
        }

        const filesBtn = (s.file_count && s.file_count > 1) ? `
            <button onclick="openSkillFilesModal('${s.id}')" class="btn-secondary btn-sm" title="Lihat ${s.file_count} File Referensi">
                <i class="fa-regular fa-folder-open" style="color:var(--accent-purple)"></i> ${s.file_count} File
            </button>
        ` : '';

        return `
            <div class="skill-card ${activeClass}" id="skill-card-${s.id}">
                <div class="skill-card-top">
                    <div class="skill-icon-wrap">${iconHtml}</div>
                    <div class="skill-meta">
                        <div class="skill-name">
                            ${escapeHtml(s.name)}
                            <span class="badge-tag ${badgeClass}">${badgeLabel}</span>
                        </div>
                        <div class="skill-desc">${escapeHtml(s.description)}</div>
                        <div style="display:flex;align-items:center;gap:6px;margin-top:6px">
                            <button onclick="togglePromptPreview('${s.id}')" class="skill-prompt-toggle" style="margin-top:0">
                                <i class="fa-solid fa-eye" style="font-size:10px"></i> Intip Prompt
                            </button>
                            ${filesBtn}
                        </div>
                        <div id="skill-prompt-${s.id}" class="skill-prompt-body">${escapeHtml(s.system_prompt)}</div>
                    </div>
                </div>
                <div class="skill-card-bottom">
                    <div style="display:flex;align-items:center;gap:8px">
                        <label class="switch">
                            <input type="checkbox" ${checked} onchange="toggleSkill('${s.id}', this.checked)">
                            <span class="slider"></span>
                        </label>
                        <span style="font-size:11.5px;color:${s.is_active ? 'var(--accent-sky)' : 'var(--text-muted)'};font-weight:600">
                            ${s.is_active ? 'Aktif' : 'Nonaktif'}
                        </span>
                    </div>
                    <div style="display:inline-flex;align-items:center;gap:6px">
                        <button onclick="openModalEditSkill('${s.id}')" class="btn-secondary btn-sm" title="Edit Skill & Prompt">
                            <i class="fa-solid fa-pen-to-square"></i> Edit
                        </button>
                        <button onclick="deleteSkill('${s.id}', '${escapeHtml(s.name)}')" class="btn-danger-ghost btn-sm" title="Hapus Skill">
                            <i class="fa-solid fa-trash-can"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function togglePromptPreview(skillId) {
    const el = document.getElementById(`skill-prompt-${skillId}`);
    if (!el) return;
    el.style.display = el.style.display === 'block' ? 'none' : 'block';
}

function openModalInstallSkill() {
    document.getElementById('modal-install-skill').classList.remove('hidden');
    document.getElementById('input-skill-name').value = '';
    document.getElementById('input-skill-desc').value = '';
    document.getElementById('input-skill-prompt').value = '';
    document.getElementById('input-skill-name').focus();
}

function closeModalInstallSkill() {
    document.getElementById('modal-install-skill').classList.add('hidden');
}

async function submitInstallSkill() {
    const name = document.getElementById('input-skill-name').value.trim();
    const icon = document.getElementById('input-skill-icon').value.trim();
    const desc = document.getElementById('input-skill-desc').value.trim();
    const prompt = document.getElementById('input-skill-prompt').value.trim();

    if (!name || !prompt) {
        showToast('Nama dan instruksi skill wajib diisi', 'error');
        return;
    }

    const btn = document.getElementById('btn-submit-skill');
    btn.disabled = true;
    btn.textContent = 'Memasang...';

    try {
        const res = await authFetch('/api/skills/install', {
            method: 'POST',
            body: JSON.stringify({
                name,
                icon: icon || 'fa-solid fa-wand-magic-sparkles',
                description: desc || 'Custom installed skill',
                system_prompt: prompt
            })
        });
        if (res.ok) {
            showToast(`Skill "${name}" berhasil dipasang dan diaktifkan!`);
            closeModalInstallSkill();
            await fetchSkills();
        } else {
            const err = await res.json();
            showToast(err.detail || 'Gagal memasang skill', 'error');
        }
    } catch (e) {
        showToast('Gagal: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Pasang Skill';
    }
}

function openModalEditSkill(skillId) {
    const skill = allLoadedSkills.find(s => s.id === skillId);
    if (!skill) return;
    document.getElementById('edit-skill-id').value = skill.id;
    document.getElementById('edit-skill-name').value = skill.name || '';
    document.getElementById('edit-skill-icon').value = skill.icon || 'fa-solid fa-wand-magic-sparkles';
    document.getElementById('edit-skill-desc').value = skill.description || '';
    document.getElementById('edit-skill-prompt').value = skill.system_prompt || '';
    document.getElementById('modal-edit-skill').classList.remove('hidden');
    document.getElementById('edit-skill-name').focus();
}

function closeModalEditSkill() {
    document.getElementById('modal-edit-skill').classList.add('hidden');
}

async function submitEditSkill() {
    const skillId = document.getElementById('edit-skill-id').value;
    const name = document.getElementById('edit-skill-name').value.trim();
    const icon = document.getElementById('edit-skill-icon').value.trim();
    const desc = document.getElementById('edit-skill-desc').value.trim();
    const prompt = document.getElementById('edit-skill-prompt').value.trim();

    if (!name || !prompt) {
        showToast('Nama dan instruksi skill wajib diisi', 'error');
        return;
    }

    const btn = document.getElementById('btn-submit-edit-skill');
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner spin"></i> Menyimpan...';

    try {
        const res = await authFetch(`/api/skills/${skillId}/update`, {
            method: 'POST',
            body: JSON.stringify({
                name,
                icon,
                description: desc,
                system_prompt: prompt
            })
        });
        if (res.ok) {
            showToast(`Skill "${name}" berhasil diperbarui!`);
            closeModalEditSkill();
            await fetchSkills();
        } else {
            const err = await res.json();
            showToast(err.detail || 'Gagal memperbarui skill', 'error');
        }
    } catch (e) {
        showToast('Gagal: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Simpan Perubahan';
    }
}

async function openSkillFilesModal(skillId) {
    const skill = allLoadedSkills.find(s => s.id === skillId);
    if (!skill) return;
    const modal = document.getElementById('modal-skill-files');
    const title = document.getElementById('skill-files-title');
    const listEl = document.getElementById('skill-files-list');
    const viewerEl = document.getElementById('skill-file-content');
    const fileNameEl = document.getElementById('skill-file-viewing-name');

    title.innerHTML = `<i class="fa-regular fa-folder-open color-purple"></i> File & Referensi: ${escapeHtml(skill.name)}`;
    listEl.innerHTML = '<div style="padding:10px;color:var(--text-muted)">Memuat file...</div>';
    viewerEl.textContent = 'Pilih file dari daftar di sebelah kiri untuk melihat isinya.';
    fileNameEl.textContent = 'Preview File';
    modal.classList.remove('hidden');

    try {
        const res = await authFetch(`/api/skills/${skillId}/files`);
        const data = await res.json();
        const files = data.files || [];
        if (files.length === 0) {
            listEl.innerHTML = '<div style="padding:10px;color:var(--text-muted)">Tidak ada file dalam skill ini.</div>';
            return;
        }

        listEl.innerHTML = files.map(f => `
            <div class="skill-file-item" onclick="loadSkillFileContent('${skillId}', '${escapeHtml(f)}', this)">
                <i class="fa-regular ${f.endsWith('.py') ? 'fa-file-code' : 'fa-file-lines'}" style="color:var(--accent-sky)"></i>
                <span style="font-family:'JetBrains Mono',monospace;font-size:11.5px">${escapeHtml(f)}</span>
            </div>
        `).join('');

        if (files.length > 0) {
            const firstItem = listEl.querySelector('.skill-file-item');
            loadSkillFileContent(skillId, files[0], firstItem);
        }
    } catch (e) {
        listEl.innerHTML = `<div style="padding:10px;color:var(--accent-rose)">Gagal: ${e.message}</div>`;
    }
}

async function loadSkillFileContent(skillId, filePath, el) {
    document.querySelectorAll('.skill-file-item').forEach(i => i.classList.remove('active'));
    if (el) el.classList.add('active');

    const viewerEl = document.getElementById('skill-file-content');
    const fileNameEl = document.getElementById('skill-file-viewing-name');
    fileNameEl.textContent = filePath;
    viewerEl.textContent = 'Memuat isi file...';

    try {
        const res = await authFetch(`/api/skills/${skillId}/files?path=${encodeURIComponent(filePath)}`);
        const data = await res.json();
        if (data.file && data.file.content !== undefined) {
            viewerEl.textContent = data.file.content;
        } else {
            viewerEl.textContent = 'File kosong atau tidak dapat dibaca.';
        }
    } catch (e) {
        viewerEl.textContent = 'Gagal memuat isi file: ' + e.message;
    }
}

function closeModalSkillFiles() {
    document.getElementById('modal-skill-files').classList.add('hidden');
}

async function toggleSkill(skillId, isActive) {
    try {
        await authFetch(`/api/skills/${skillId}/toggle`, {
            method: 'POST',
            body: JSON.stringify({ is_active: isActive })
        });
        showToast(isActive ? 'Skill diaktifkan' : 'Skill dinonaktifkan');
        await fetchSkills();
    } catch (e) {
        showToast('Gagal mengubah status skill', 'error');
    }
}

async function deleteSkill(skillId, name) {
    if (!confirm(`Hapus skill "${name}"? Tindakan ini akan menghapus skill dan file SKILL.md terkait.`)) return;
    try {
        const res = await authFetch(`/api/skills/${skillId}`, { method: 'DELETE' });
        if (res.ok) {
            showToast(`Skill "${name}" berhasil dihapus`);
            await fetchSkills();
        } else {
            const err = await res.json();
            showToast(err.detail || 'Gagal menghapus skill', 'error');
        }
    } catch (e) {
        showToast('Gagal menghapus: ' + e.message, 'error');
    }
}

function openModalChangePass() {
    document.getElementById('modal-change-pass').classList.remove('hidden');
    document.getElementById('input-curr-pass').value = '';
    document.getElementById('input-new-pass').value = '';
    document.getElementById('input-confirm-pass').value = '';
}

function closeModalChangePass() {
    document.getElementById('modal-change-pass').classList.add('hidden');
}

async function submitChangePassword() {
    const curr = document.getElementById('input-curr-pass').value;
    const newp = document.getElementById('input-new-pass').value;
    const conf = document.getElementById('input-confirm-pass').value;
    if (!curr || !newp) { showToast('Isi semua field', 'error'); return; }
    if (newp !== conf) { showToast('Konfirmasi tidak cocok', 'error'); return; }
    if (newp.length < 6) { showToast('Min. 6 karakter', 'error'); return; }

    const btn = document.getElementById('btn-save-pass');
    btn.disabled = true;
    btn.textContent = 'Menyimpan...';
    try {
        await changePassword(curr, newp);
        showToast('Password diubah — silakan login ulang');
        closeModalChangePass();
        setTimeout(performLogout, 1500);
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Simpan';
    }
}

// ==========================================================================
// File / Image Attachment System
// ==========================================================================
function setupFileDropAndPaste() {
    const dropZone = document.getElementById('input-drop-zone') || document.querySelector('.input-area');
    const textarea = document.getElementById('prompt-input');

    if (dropZone) {
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.add('drag-over');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.remove('drag-over');
            }, false);
        });

        dropZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            if (dt && dt.files && dt.files.length > 0) {
                processFiles(dt.files);
            }
        });
    }

    if (textarea) {
        textarea.addEventListener('paste', (e) => {
            const items = (e.clipboardData || e.originalEvent.clipboardData)?.items;
            if (!items) return;
            const files = [];
            for (let i = 0; i < items.length; i++) {
                if (items[i].kind === 'file') {
                    const f = items[i].getAsFile();
                    if (f) files.push(f);
                }
            }
            if (files.length > 0) {
                processFiles(files);
            }
        });
    }
}

function triggerFileInput() {
    const input = document.getElementById('chat-file-input');
    if (input) input.click();
}

function handleFileSelect(event) {
    const files = event.target.files;
    if (files && files.length > 0) {
        processFiles(files);
    }
    event.target.value = '';
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

function processFiles(fileList) {
    for (let i = 0; i < fileList.length; i++) {
        const file = fileList[i];
        if (attachedFiles.some(f => f.name === file.name && f.size === file.size)) continue;

        const isImg = file.type.startsWith('image/') || /\.(jpg|jpeg|png|webp|gif|bmp)$/i.test(file.name);
        const isPdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name);
        const isText = file.type.startsWith('text/') || 
            /\.(py|js|ts|jsx|tsx|html|css|json|csv|md|txt|log|sh|bat|sql|yaml|yml|xml|toml|ini)$/i.test(file.name);

        const fileObj = {
            id: 'f-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6),
            file: file,
            name: file.name,
            size: file.size,
            sizeFormatted: formatFileSize(file.size),
            type: file.type || 'file',
            isImage: isImg,
            isPdf: isPdf,
            isText: isText,
            dataUrl: null,
            content: null,
            statusText: ''
        };

        if (isImg) {
            const reader = new FileReader();
            reader.onload = async (e) => {
                fileObj.dataUrl = e.target.result;
                fileObj.statusText = '⏳ OCR berjalan...';
                renderAttachedFiles();

                if (window.Tesseract) {
                    try {
                        const res = await Tesseract.recognize(fileObj.dataUrl, 'eng+ind');
                        if (res && res.data && res.data.text && res.data.text.trim()) {
                            fileObj.content = res.data.text.trim();
                            fileObj.statusText = '✓ OCR Selesai';
                        } else {
                            fileObj.statusText = '✓ Gambar siap';
                        }
                    } catch (err) {
                        fileObj.statusText = '✓ Gambar siap';
                    }
                    renderAttachedFiles();
                } else {
                    fileObj.statusText = '✓ Gambar siap';
                    renderAttachedFiles();
                }
            };
            reader.readAsDataURL(file);
        } else if (isPdf) {
            const reader = new FileReader();
            reader.onload = async (e) => {
                fileObj.statusText = '⏳ Ekstraksi PDF...';
                renderAttachedFiles();
                try {
                    if (window.pdfjsLib) {
                        pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
                        const typedarray = new Uint8Array(e.target.result);
                        const pdf = await pdfjsLib.getDocument(typedarray).promise;
                        let fullPdfText = '';
                        const maxPages = Math.min(pdf.numPages, 30);
                        for (let pageNum = 1; pageNum <= maxPages; pageNum++) {
                            const page = await pdf.getPage(pageNum);
                            const textContent = await page.getTextContent();
                            const pageText = textContent.items.map(item => item.str).join(' ');
                            fullPdfText += `\n--- Halaman ${pageNum} ---\n` + pageText;
                        }
                        fileObj.content = fullPdfText.trim();
                        fileObj.statusText = `✓ PDF (${pdf.numPages} hal) Siap`;
                    }
                } catch (err) {
                    fileObj.statusText = '✓ PDF terlampir';
                }
                renderAttachedFiles();
            };
            reader.readAsArrayBuffer(file);
        } else if (isText && file.size < 1048576 * 5) {
            const reader = new FileReader();
            reader.onload = (e) => {
                fileObj.content = e.target.result;
                fileObj.statusText = '✓ Teks dibaca';
                renderAttachedFiles();
            };
            reader.readAsText(file);
        }

        attachedFiles.push(fileObj);
    }
    renderAttachedFiles();
}

function removeAttachedFile(id) {
    attachedFiles = attachedFiles.filter(f => f.id !== id);
    renderAttachedFiles();
}

function renderAttachedFiles() {
    const container = document.getElementById('attached-files-container');
    if (!container) return;

    if (attachedFiles.length === 0) {
        container.style.display = 'none';
        container.innerHTML = '';
        return;
    }

    container.style.display = 'flex';
    container.innerHTML = attachedFiles.map(f => {
        let iconHtml = '<i class="fa-solid fa-file-lines" style="color:var(--accent-sky)"></i>';
        if (f.isImage && f.dataUrl) {
            iconHtml = `<img src="${f.dataUrl}" class="file-thumb" alt="thumb">`;
        } else if (f.isPdf) {
            iconHtml = '<i class="fa-solid fa-file-pdf" style="color:var(--accent-rose)"></i>';
        } else if (f.name.endsWith('.py') || f.name.endsWith('.js') || f.name.endsWith('.ts')) {
            iconHtml = '<i class="fa-solid fa-file-code" style="color:var(--accent-purple)"></i>';
        } else if (f.isImage) {
            iconHtml = '<i class="fa-solid fa-file-image" style="color:var(--accent-emerald)"></i>';
        }

        const statusBadge = f.statusText ? `<span style="font-size:10px;color:var(--accent-emerald);margin-left:2px">${escapeHtml(f.statusText)}</span>` : '';

        return `
            <div class="attached-file-chip" id="${f.id}">
                ${iconHtml}
                <span class="file-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
                <span class="file-size">(${f.sizeFormatted})</span>
                ${statusBadge}
                <button type="button" class="file-remove" onclick="removeAttachedFile('${f.id}')" title="Hapus file">&times;</button>
            </div>
        `;
    }).join('');
}

// ==========================================================================
// Chat Messaging & Response Handling
// ==========================================================================
async function sendMessage() {
    if (isGenerating) return;
    const input = document.getElementById('prompt-input');
    const rawPrompt = input.value.trim();
    if (!rawPrompt && attachedFiles.length === 0) return;

    input.value = '';
    isGenerating = true;
    const btnSend = document.getElementById('btn-send');
    btnSend.disabled = true;

    const container = document.getElementById('messages-container');
    const model = document.getElementById('chat-model').value;
    const accountSelect = document.getElementById('chat-account');
    const selectedAccount = accountSelect ? accountSelect.value : 'auto';
    const boostEnabled = document.getElementById('chat-boost') ? document.getElementById('chat-boost').checked : false;
    const searchEnabled = document.getElementById('chat-search') ? document.getElementById('chat-search').checked : true;

    // Build user message bubble with thumbnails if images attached
    const currentFiles = [...attachedFiles];
    attachedFiles = [];
    renderAttachedFiles();

    let userBubbleContent = '';
    currentFiles.forEach(f => {
        if (f.isImage && f.dataUrl) {
            userBubbleContent += `<img src="${f.dataUrl}" class="chat-attached-image" alt="${escapeHtml(f.name)}">`;
        } else {
            userBubbleContent += `<div style="font-size:11px;opacity:0.85;margin-bottom:4px"><i class="fa-solid fa-paperclip"></i> ${escapeHtml(f.name)} (${f.sizeFormatted}) ${f.statusText ? `· ${escapeHtml(f.statusText)}` : ''}</div>`;
        }
    });
    if (rawPrompt) {
        userBubbleContent += `<div>${escapeHtml(rawPrompt)}</div>`;
    }

    const userBubble = document.createElement('div');
    userBubble.className = 'message-user';
    userBubble.innerHTML = `<div class="message-user-bubble">${userBubbleContent}</div>`;
    container.appendChild(userBubble);

    // Build prompt sent to model (inject text attachments / OCR results if any)
    let fullPrompt = rawPrompt || '';
    currentFiles.forEach(f => {
        if (f.content) {
            let label = 'Isi Berkas';
            if (f.isPdf) label = 'Hasil Ekstraksi Teks PDF';
            else if (f.isImage) label = 'Hasil Ekstraksi OCR Teks Gambar';
            fullPrompt += `\n\n--- [${label}: ${f.name}] ---\n${f.content}\n--- [Akhir ${f.name}] ---\n`;
        } else if (f.isImage) {
            fullPrompt += `\n\n[Pengguna melampirkan berkas gambar: ${f.name} (${f.sizeFormatted})]`;
        } else {
            fullPrompt += `\n\n[Pengguna melampirkan berkas: ${f.name} (${f.sizeFormatted})]`;
        }
    });

    const msgId = 'msg-' + Date.now();
    const aiBubble = document.createElement('div');
    aiBubble.className = 'message-ai';
    aiBubble.innerHTML = `
        <div class="ai-avatar"><i class="fa-solid fa-robot"></i></div>
        <div class="ai-bubble">
            <div id="${msgId}-search" class="search-indicator" style="display:none">
                <i class="fa-solid fa-globe spin"></i>
                <span id="${msgId}-search-text">Menelusuri web...</span>
            </div>

            <!-- Background Reasoning Loader (Konsep Bersih: nalar jalan di background tanpa terlihat) -->
            <div id="${msgId}-reasoning" class="reasoning-loader" style="display:none">
                <div class="reasoning-spinner">
                    <i class="fa-solid fa-brain pulse color-purple"></i>
                </div>
                <div class="reasoning-text-group">
                    <span class="reasoning-title">Sedang bernalar di latar belakang...</span>
                    <span class="reasoning-subtitle">DeepSeek R1 reasoning aktif, menyiapkan jawaban terbaik</span>
                </div>
            </div>

            <div id="${msgId}-text" class="ai-rendered-content">
                <span class="loading-spinner"><i class="fa-solid fa-spinner spin"></i> Menghubungkan...</span>
            </div>
            <div id="${msgId}-footer" class="msg-footer" style="display:none">
                <button onclick="copyMsgText('${msgId}-text')" class="btn-copy-msg"><i class="fa-regular fa-copy"></i> Salin</button>
            </div>
        </div>`;
    container.appendChild(aiBubble);
    container.scrollTop = container.scrollHeight;

    const searchEl = document.getElementById(`${msgId}-search`);
    const searchText = document.getElementById(`${msgId}-search-text`);
    const reasoningLoader = document.getElementById(`${msgId}-reasoning`);
    const textEl = document.getElementById(`${msgId}-text`);
    const footerEl = document.getElementById(`${msgId}-footer`);

    let fullText = '';
    let fullThinking = '';
    let searchCompleted = false;

    try {
        const response = await authFetch('/api/chat', {
            method: 'POST',
            body: JSON.stringify({
                prompt: fullPrompt,
                model,
                account: selectedAccount,
                thinking_enabled: true,
                boost_enabled: boostEnabled,
                search_enabled: searchEnabled,
                session_id: currentSessionId
            })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Error ' + response.status }));
            if (reasoningLoader) reasoningLoader.style.display = 'none';
            if (searchEl) searchEl.style.display = 'none';
            textEl.innerHTML = `<span class="color-rose">❌ ${escapeHtml(err.detail || 'Gagal')}</span>`;
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const dataStr = line.slice(6).trim();
                if (dataStr === '[DONE]') break;
                try {
                    const payload = JSON.parse(dataStr);
                    if (payload.session_id) currentSessionId = payload.session_id;

                    if (payload.type === 'search_status') {
                        searchEl.style.display = 'flex';
                        searchText.textContent = payload.content;
                    } else if (payload.type === 'search_results') {
                        try {
                            const sources = JSON.parse(payload.content);
                            searchCompleted = true;
                            searchEl.style.display = 'flex';
                            searchText.innerHTML = `✓ ${sources.length} referensi web ditemukan`;
                            const icon = searchEl.querySelector('i');
                            if (icon) {
                                icon.className = 'fa-solid fa-circle-check color-emerald';
                            }
                        } catch {}
                    } else if (payload.type === 'thinking') {
                        // Nalar DeepSeek R1 disimpan di background dan tidak diperlihatkan sebagai teks
                        fullThinking += payload.content;
                        if (reasoningLoader && !fullText) {
                            reasoningLoader.style.display = 'flex';
                            textEl.style.display = 'none';
                        }
                    } else if (payload.type === 'text') {
                        // Selesai nalar: sembunyikan loader dan langsung tampilkan teks hasil
                        if (reasoningLoader) reasoningLoader.style.display = 'none';
                        if (searchEl && !searchCompleted) {
                            searchEl.style.display = 'none';
                        }
                        textEl.style.display = 'block';
                        fullText += payload.content;
                        textEl.innerHTML = cleanRenderMarkdown(fullText);
                    }
                    container.scrollTop = container.scrollHeight;
                } catch {}
            }
        }

        if (reasoningLoader) reasoningLoader.style.display = 'none';
        if (searchEl && !searchCompleted) {
            searchEl.style.display = 'none';
        }
        textEl.style.display = 'block';
        footerEl.style.display = 'flex';

        if (!fullText && fullThinking) {
            textEl.innerHTML = cleanRenderMarkdown(fullThinking);
        }

    } catch (err) {
        if (reasoningLoader) reasoningLoader.style.display = 'none';
        if (searchEl) searchEl.style.display = 'none';
        textEl.style.display = 'block';
        textEl.innerHTML = `<span class="color-rose">❌ Koneksi gagal: ${escapeHtml(err.message)}</span>`;
    } finally {
        isGenerating = false;
        btnSend.disabled = false;
    }
}

function clearChat() {
    currentSessionId = null;
    const container = document.getElementById('messages-container');
    container.innerHTML = `
        <div class="message-ai">
            <div class="ai-avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="ai-bubble">
                <div class="ai-rendered-content">
                    <strong>Percakapan baru.</strong> Deep Thinking (Latar Belakang) &amp; Web Search aktif. Tanya apa saja!
                </div>
            </div>
        </div>`;
}
