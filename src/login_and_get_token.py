import time
import json
from pathlib import Path
from DrissionPage import ChromiumPage

def main():
    print("\n" + "=" * 60)
    print("🚀 DeepSeek Auto Token & Cookie Grabber")
    print("=" * 60)
    print("Membuka browser Chrome...")

    try:
        driver = ChromiumPage()
    except Exception as e:
        print(f"❌ Gagal membuka Chrome: {e}")
        return

    driver.get("https://chat.deepseek.com")
    print("👉 Silakan LOGIN ke akun DeepSeek Anda di jendela browser yang terbuka.")
    print("⏳ Menunggu Anda login (script otomatis mendeteksi jika sudah login)...")

    token = None
    max_wait = 300  # 5 menit batas tunggu
    start_time = time.time()

    while time.time() - start_time < max_wait:
        try:
            raw_token = driver.run_js('return localStorage.getItem("userToken");')
            if raw_token:
                try:
                    parsed = json.loads(raw_token)
                    token = parsed.get("value", raw_token)
                except Exception:
                    token = raw_token
                break
        except Exception:
            pass
        time.sleep(2)

    if not token:
        print("\n❌ Waktu tunggu habis. Belum berhasil login.")
        driver.quit()
        return

    print("\n🎉 BERHASIL! userToken login berhasil ditangkap!")

    # 1. Simpan ke .env
    env_path = Path(__file__).parent / ".env"
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(f"DEEPSEEK_AUTH_TOKEN={token}\n")
    print(f"✅ Token berhasil disimpan ke file: {env_path.resolve()}")

    # 2. Tangkap semua cookie terbaru langsung dari browser
    cookies = {}
    try:
        for c in driver.cookies():
            name = c.get("name")
            val = c.get("value")
            if name and val:
                cookies[name] = val

        cookies_file = Path(__file__).parent / "dsk" / "cookies.json"
        cookies_data = {
            "cookies": cookies,
            "user_agent": driver.user_agent
        }
        with open(cookies_file, "w", encoding="utf-8") as f:
            json.dump(cookies_data, f, indent=4)
        print(f"✅ Cookies ({len(cookies)} cookies) berhasil disimpan ke: {cookies_file.resolve()}")
    except Exception as e:
        print(f"⚠️ Gagal menyimpan cookies: {e}")

    print("\n" + "=" * 60)
    print("✨ SEMUA SELESAI! Anda sekarang bisa menjalankan:")
    print("   .venv\\Scripts\\python.exe example.py")
    print("=" * 60 + "\n")

    driver.quit()

if __name__ == "__main__":
    main()
