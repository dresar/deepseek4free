const AUTH_TOKEN_KEY = 'dsk4f_token';
const AUTH_USER_KEY = 'dsk4f_user';

function getStoredToken() {
    return localStorage.getItem(AUTH_TOKEN_KEY);
}

function setStoredToken(token, username) {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
    localStorage.setItem(AUTH_USER_KEY, username);
}

function clearStoredToken() {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(AUTH_USER_KEY);
}

function getStoredUser() {
    return localStorage.getItem(AUTH_USER_KEY) || 'admin';
}

function isLoginPage() {
    return window.location.pathname === '/login';
}

async function authFetch(url, options = {}) {
    const token = getStoredToken();
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    return fetch(url, { ...options, headers });
}

async function checkAuthStatus() {
    const token = getStoredToken();
    if (!token) return false;
    try {
        const res = await fetch('/api/auth/me', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        return res.ok;
    } catch {
        return false;
    }
}

async function performLogin(username, password) {
    const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Login gagal' }));
        throw new Error(err.detail || 'Login gagal');
    }
    const data = await res.json();
    setStoredToken(data.token, data.username);
    return data;
}

async function performLogout() {
    const token = getStoredToken();
    if (token) {
        await fetch('/api/auth/logout', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        }).catch(() => {});
    }
    clearStoredToken();
    window.location.replace('/login');
}

async function changePassword(currentPassword, newPassword) {
    const res = await authFetch('/api/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Gagal mengubah password' }));
        throw new Error(err.detail || 'Gagal mengubah password');
    }
    return res.json();
}

async function initApp() {
    const isAuthed = await checkAuthStatus();
    if (!isAuthed) {
        clearStoredToken();
        window.location.replace('/login');
        return false;
    }
    const userDisplay = document.getElementById('header-user');
    if (userDisplay) userDisplay.textContent = getStoredUser();
    return true;
}
