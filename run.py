"""Local launcher with automatic environment setup and first frontend build."""
from pathlib import Path
import os
import argparse
import shutil
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
    parser=argparse.ArgumentParser(description='Запуск MoneyGraph AI')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    if not 1024<=args.port<=65535:
        parser.error('Порт должен быть от 1024 до 65535')
    url=f'http://127.0.0.1:{args.port}'
    os.chdir(ROOT)
    if not PYTHON.exists():
        subprocess.run([sys.executable,'-m','venv',str(VENV)],check=True)
    if Path(sys.prefix).resolve()!=VENV.resolve():
        subprocess.run([str(PYTHON),str(ROOT/'run.py'),'--port',str(args.port)],check=True)
        return
    try:
        import fastapi, uvicorn, pandas, networkx, sklearn, openai, multipart, dotenv, pyarrow
    except ImportError:
        subprocess.run([str(PYTHON),'-m','pip','install','-r',str(ROOT/'requirements-lock.txt')],check=True)
    if not (ROOT/'frontend/dist/index.html').exists():
        pnpm=shutil.which('pnpm')
        if not pnpm:
            raise SystemExit('Для первой сборки установите Node.js и pnpm. В папке frontend выполните pnpm install и pnpm build.')
        prefix=['cmd','/c',pnpm] if os.name=='nt' else [pnpm]
        subprocess.run(prefix+['install','--frozen-lockfile'],cwd=ROOT/'frontend',check=True)
        subprocess.run(prefix+['build'],cwd=ROOT/'frontend',check=True)
    def open_when_ready():
        for _ in range(60):
            try:
                with urllib.request.urlopen(url+'/api/health',timeout=1) as response:
                    if response.status==200:
                        webbrowser.open(url)
                        return
            except Exception:
                time.sleep(1)
    threading.Thread(target=open_when_ready,daemon=True).start()
    print(f'MoneyGraph AI: {url} | Ctrl+C — остановить',flush=True)
    subprocess.run([str(PYTHON),'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',str(args.port)],check=True)

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
