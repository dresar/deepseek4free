async function init() {
  const statusEl = document.getElementById('status');
  const tokenBox = document.getElementById('tokenBox');
  const btnCopy = document.getElementById('btnCopy');
  const btnDownload = document.getElementById('btnDownload');

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.url || !tab.url.includes('chat.deepseek.com')) {
    statusEl.className = 'status error';
    statusEl.innerText = '⚠️ Silakan buka tab chat.deepseek.com terlebih dahulu!';
    return;
  }

  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        try {
          const raw = localStorage.getItem('userToken');
          if (!raw) return { error: 'Belum login di chat.deepseek.com! Silakan login akun dulu.' };
          try {
            const parsed = JSON.parse(raw);
            return { token: parsed.value || raw };
          } catch (e) {
            return { token: raw };
          }
        } catch (err) {
          return { error: 'Gagal membaca: ' + err.message };
        }
      }
    });

    const res = results && results[0] && results[0].result;
    if (!res || res.error) {
      statusEl.className = 'status error';
      statusEl.innerText = '❌ ' + (res ? res.error : 'Gagal mengakses halaman.');
      return;
    }

    const token = res.token;
    statusEl.className = 'status success';
    statusEl.innerText = '✅ userToken berhasil ditemukan!';
    tokenBox.value = token;
    btnCopy.style.display = 'block';
    btnDownload.style.display = 'block';

    btnCopy.addEventListener('click', async () => {
      await navigator.clipboard.writeText(token);
      btnCopy.innerText = '✅ Berhasil Disalin!';
      setTimeout(() => btnCopy.innerText = '📋 Salin Token (Copy)', 2000);
    });

    btnDownload.addEventListener('click', () => {
      const blob = new Blob([`DEEPSEEK_AUTH_TOKEN=${token}\n`], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = '.env';
      a.click();
      URL.revokeObjectURL(url);
    });

  } catch (e) {
    statusEl.className = 'status error';
    statusEl.innerText = '❌ Error: ' + e.message;
  }
}

document.addEventListener('DOMContentLoaded', init);
