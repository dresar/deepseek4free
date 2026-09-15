import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

def build_windows_exe(onefile=False):
    output_mode = '--onefile' if onefile else '--onedir'
    name = 'deepseek-server'
    web_dir = str(ROOT / 'web')
    wasm_dir = str(ROOT / 'dsk' / 'wasm')
    
    cmd = [
        sys.executable,
        '-m', 'PyInstaller',
        '--noconfirm',
        output_mode,
        '--name', name,
        '--add-data', f'{web_dir};web',
        '--add-data', f'{wasm_dir};dsk/wasm',
        '--collect-all', 'wasmtime',
        '--collect-all', 'curl_cffi',
        '--hidden-import', 'uvicorn',
        '--hidden-import', 'uvicorn.logging',
        '--hidden-import', 'uvicorn.loops',
        '--hidden-import', 'uvicorn.loops.auto',
        '--hidden-import', 'uvicorn.protocols',
        '--hidden-import', 'uvicorn.protocols.http',
        '--hidden-import', 'uvicorn.protocols.http.auto',
        '--hidden-import', 'uvicorn.protocols.http.h11_impl',
        '--hidden-import', 'uvicorn.protocols.websockets',
        '--hidden-import', 'uvicorn.protocols.websockets.auto',
        '--hidden-import', 'uvicorn.lifespan',
        '--hidden-import', 'uvicorn.lifespan.on',
        '--hidden-import', 'uvicorn.lifespan.off',
        '--hidden-import', 'fastapi',
        '--hidden-import', 'starlette',
        '--hidden-import', 'pydantic',
        '--hidden-import', 'curl_cffi',
        '--hidden-import', 'requests',
        '--hidden-import', 'wasmtime',
        '--hidden-import', 'numpy',
        '--hidden-import', 'dotenv',
        str(ROOT / 'server.py')
    ]
    
    print('Executing PyInstaller...')
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode == 0:
        print("=" * 60)
        print("BUILD EXE BERHASIL!")
        dist_path = ROOT / "dist" / (f"{name}.exe" if onefile else name)
        print(f"Output: {dist_path}")
        print("=" * 60)
    else:
        print(f"Build gagal dengan returncode: {result.returncode}")

if __name__ == '__main__':
    is_onefile = '--onefile' in sys.argv
    build_windows_exe(onefile=is_onefile)
