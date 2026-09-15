let currentSessionId = null;
let isGenerating = false;
let currentTab = 'playground';

document.addEventListener('DOMContentLoaded', async () => {
    const ready = await initApp();
    if (!ready) return;

    document.getElementById('api-base-url').textContent = window.location.origin + '/v1';

    setupToggleChips();
    setupKeyboardShortcuts();
    await fetchPoolStatus();
    setInterval(fetchPoolStatus, 8000);
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
    ['playground', 'pool', 'settings'].forEach(t => {
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
}

function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<i class="fa-solid ${type === 'success' ? 'fa-circle-check' : 'fa-circle-xmark'}"></i> ${message}`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

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
    } catch {}
}

function renderTokensTable(tokens) {
    const tbody = document.getElementById('tokens-tbody');
    if (!tbody) return;
    if (tokens.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Belum ada akun di pool</td></tr>';
        return;
    }
    tbody.innerHTML = tokens.map((t, i) => {
        let badge = '';
        if (t.status === 'healthy') {
            badge = '<span class="status-badge badge-healthy">Aktif</span>';
        } else if (t.status === 'cooldown') {
            badge = `<span class="status-badge badge-cooldown">Cooldown ${t.cooldown_remaining.toFixed(0)}s</span>`;
        } else {
            badge = '<span class="status-badge badge-invalid">Invalid</span>';
        }
        const lat = t.latency_ms > 0 ? `${t.latency_ms.toFixed(0)}ms` : '—';
        const reqs = `${t.total_successes}/${t.total_successes + t.total_errors}`;
        const err = t.last_error ? `<span class="color-rose" title="${escapeHtml(t.last_error)}" style="cursor:help">${escapeHtml(t.last_error.slice(0, 32))}${t.last_error.length > 32 ? '…' : ''}</span>` : '—';

        return `<tr>
            <td style="color:var(--text-muted)">${i + 1}</td>
            <td style="color:var(--text-primary);font-weight:600">${escapeHtml(t.name)}</td>
            <td>${badge}</td>
            <td class="color-purple">${lat}</td>
            <td>${reqs}</td>
            <td>${err}</td>
            <td style="text-align:right">
                <button onclick="removeToken('${escapeHtml(t.name)}')" class="btn-danger-ghost" title="Hapus">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
            </td>
        </tr>`;
    }).join('');
}

async function triggerLearn() {
    const btn = document.getElementById('btn-learn');
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner spin"></i> Benchmark...';
    try {
        const res = await authFetch('/api/learn', { method: 'POST' });
        const result = await res.json();
        showToast(`/learn selesai — Valid: ${result.valid || 0}`);
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
        showToast(`+${data.added} token ditambahkan`);
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
    if (!confirm(`Hapus akun "${tokenName}"?`)) return;
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
    try {
        const res = await authFetch('/api/settings', {
            method: 'POST',
            body: JSON.stringify({ strategy, boost_enabled: boost })
        });
        if (res.ok) {
            showToast('Pengaturan disimpan');
            await fetchPoolStatus();
        }
    } catch (e) {
        showToast('Gagal menyimpan', 'error');
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

async function sendMessage() {
    if (isGenerating) return;
    const input = document.getElementById('prompt-input');
    const prompt = input.value.trim();
    if (!prompt) return;

    input.value = '';
    isGenerating = true;
    const btnSend = document.getElementById('btn-send');
    btnSend.disabled = true;

    const container = document.getElementById('messages-container');
    const model = document.getElementById('chat-model').value;
    const thinkingEnabled = document.getElementById('chat-thinking').checked;
    const boostEnabled = document.getElementById('chat-boost').checked;
    const searchEnabled = document.getElementById('chat-search').checked;

    const userBubble = document.createElement('div');
    userBubble.className = 'message-user';
    userBubble.innerHTML = `<div class="message-user-bubble">${escapeHtml(prompt)}</div>`;
    container.appendChild(userBubble);

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
            <div id="${msgId}-thinking" class="thinking-box" style="display:none">
                <button onclick="toggleThinking('${msgId}')" class="thinking-header">
                    <span><i class="fa-solid fa-brain"></i> Deep Thinking</span>
                    <div style="display:flex;align-items:center;gap:6px">
                        <span id="${msgId}-thinking-status" class="pulse" style="font-size:10px;color:var(--accent-purple)">Bernalar...</span>
                        <i id="${msgId}-thinking-icon" class="fa-solid fa-chevron-down" style="font-size:9px"></i>
                    </div>
                </button>
                <div id="${msgId}-thinking-body" class="thinking-body"></div>
            </div>
            <div id="${msgId}-text" class="ai-rendered-content">
                <span class="loading-spinner"><i class="fa-solid fa-spinner spin"></i> Menghubungkan...</span>
            </div>
            <div id="${msgId}-footer" class="msg-footer" style="display:none">
                <span id="${msgId}-account" class="msg-account-tag"><i class="fa-solid fa-shield-halved" style="font-size:9px"></i> Pool</span>
                <button onclick="copyMsgText('${msgId}-text')" class="btn-copy-msg"><i class="fa-regular fa-copy"></i> Salin</button>
            </div>
        </div>`;
    container.appendChild(aiBubble);
    container.scrollTop = container.scrollHeight;

    const searchEl = document.getElementById(`${msgId}-search`);
    const searchText = document.getElementById(`${msgId}-search-text`);
    const thinkingEl = document.getElementById(`${msgId}-thinking`);
    const thinkingStatus = document.getElementById(`${msgId}-thinking-status`);
    const thinkingBody = document.getElementById(`${msgId}-thinking-body`);
    const textEl = document.getElementById(`${msgId}-text`);
    const footerEl = document.getElementById(`${msgId}-footer`);
    const accountEl = document.getElementById(`${msgId}-account`);

    if (searchEnabled) searchEl.style.display = 'flex';

    let fullText = '';
    let fullThinking = '';

    try {
        const response = await authFetch('/api/chat', {
            method: 'POST',
            body: JSON.stringify({
                prompt,
                model,
                thinking_enabled: thinkingEnabled,
                boost_enabled: boostEnabled,
                search_enabled: searchEnabled,
                session_id: currentSessionId
            })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Error ' + response.status }));
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
                    if (payload.token_used) {
                        accountEl.innerHTML = `<i class="fa-solid fa-shield-halved" style="font-size:9px"></i> ${escapeHtml(payload.token_used)}`;
                    }
                    if (payload.type === 'search_status') {
                        searchEl.style.display = 'flex';
                        searchText.textContent = payload.content;
                    } else if (payload.type === 'search_results') {
                        try {
                            const sources = JSON.parse(payload.content);
                            searchText.innerHTML = `✓ ${sources.length} referensi ditemukan`;
                            searchEl.querySelector('i').classList.remove('spin');
                        } catch {}
                    } else if (payload.type === 'thinking') {
                        thinkingEl.style.display = 'block';
                        fullThinking += payload.content;
                        thinkingBody.textContent = fullThinking;
                    } else if (payload.type === 'text') {
                        thinkingStatus.textContent = 'Selesai';
                        thinkingStatus.classList.remove('pulse');
                        fullText += payload.content;
                        textEl.innerHTML = cleanRenderMarkdown(fullText);
                    }
                    container.scrollTop = container.scrollHeight;
                } catch {}
            }
        }

        footerEl.style.display = 'flex';
        if (!fullText && fullThinking) {
            textEl.innerHTML = cleanRenderMarkdown(fullThinking);
        }

    } catch (err) {
        textEl.innerHTML = `<span class="color-rose">❌ Koneksi gagal: ${escapeHtml(err.message)}</span>`;
    } finally {
        isGenerating = false;
        btnSend.disabled = false;
    }
}

function toggleThinking(msgId) {
    const body = document.getElementById(`${msgId}-thinking-body`);
    const icon = document.getElementById(`${msgId}-thinking-icon`);
    const hidden = body.style.display === 'none';
    body.style.display = hidden ? 'block' : 'none';
    icon.className = `fa-solid ${hidden ? 'fa-chevron-down' : 'fa-chevron-right'}`;
    icon.style.fontSize = '9px';
}

function clearChat() {
    currentSessionId = null;
    const container = document.getElementById('messages-container');
    container.innerHTML = `
        <div class="message-ai">
            <div class="ai-avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="ai-bubble">
                <div class="ai-rendered-content">
                    <strong>Percakapan baru.</strong> Tanyakan apa saja.
                </div>
            </div>
        </div>`;
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => showToast('Tersalin!'));
}

function copyMsgText(elId) {
    const el = document.getElementById(elId);
    if (el) {
        navigator.clipboard.writeText(el.innerText).then(() => showToast('Tersalin!'));
    }
}
