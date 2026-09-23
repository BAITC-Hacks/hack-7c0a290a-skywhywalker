"""Local launcher. Build frontend with pnpm build before first run."""
from pathlib import Path
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parent
VENV=ROOT/'.venv'
PYTHON=VENV/('Scripts/python.exe' if os.name=='nt' else 'bin/python')

def main():
    os.chdir(ROOT)
    if not PYTHON.exists():
        subprocess.run([sys.executable,'-m','venv',str(VENV)],check=True)
    if Path(sys.prefix).resolve()!=VENV.resolve():
        subprocess.run([str(PYTHON),str(ROOT/'run.py')],check=True)
        return
    try:
        import fastapi, uvicorn, pandas, networkx, sklearn, openai, multipart, dotenv
    except ImportError:
        subprocess.run([str(PYTHON),'-m','pip','install','-r',str(ROOT/'requirements-lock.txt')],check=True)
    if not (ROOT/'frontend/dist/index.html').exists():
        raise SystemExit('Интерфейс не собран. В папке frontend выполните pnpm install и pnpm build.')
    def open_when_ready():
        for _ in range(60):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=1) as response:
                    if response.status==200:
                        webbrowser.open('http://127.0.0.1:8000')
                        return
            except Exception:
                time.sleep(1)
    threading.Thread(target=open_when_ready,daemon=True).start()
    print('MoneyGraph AI: http://127.0.0.1:8000 | Ctrl+C — остановить',flush=True)
    subprocess.run([str(PYTHON),'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000'],check=True)

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
