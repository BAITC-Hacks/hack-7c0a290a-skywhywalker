import os
import re
import time
import uuid
from pathlib import Path
from threading import RLock
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, HTTPException, Header, Query, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from .graph_engine import parse_csv, hop_nodes
from .analysis import Analysis
from .models import NodeRequest, CompareRequest, ChatRequest
from . import ai_copilot

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
store = {}
lock = RLock()
MAX_BYTES = 5*1024*1024

@asynccontextmanager
async def lifespan(app):
    df = parse_csv((ROOT/'data/sample_transactions.csv').read_bytes())
    store['demo'] = {'df':df,'filename':'sample_transactions.csv','analysis':Analysis(df,'sample_transactions.csv'),'time':time.time()}
    yield

app = FastAPI(title='MoneyGraph AI',version='1.0.0',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:5173','http://localhost:5173'],allow_methods=['GET','POST'],allow_headers=['Content-Type','X-Dataset-ID'])

def dataset(x_dataset_id: str = Header(default='demo')):
    with lock:
        entry = store.get(x_dataset_id)
        if entry is None:
            raise HTTPException(404,'Набор данных не найден. Загрузите CSV повторно.')
        entry['time'] = time.time()
        return entry

def analyzed(entry=Depends(dataset)):
    if entry['analysis'] is None:
        raise HTTPException(409,'Сначала нажмите «Построить граф».')
    return entry['analysis']

def require_node(a,node):
    if node not in a.nodes:
        raise HTTPException(404,'Счёт не найден.')

@app.get('/api/health')
def health():
    return {'status':'ok','ai_configured':os.getenv('OPENAI_API_KEY','') not in ('','your_key_here')}

@app.post('/api/upload')
async def upload(file:UploadFile=File(...)):
    raw = await file.read(MAX_BYTES+1)
    await file.close()
    if len(raw)>MAX_BYTES:
        raise HTTPException(413,'Максимальный размер CSV — 5 MB.')
    try:
        df = parse_csv(raw)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    with lock:
        for k in list(store):
            if k!='demo' and time.time()-store[k]['time']>7200:
                del store[k]
        if len(store)>=9:
            raise HTTPException(429,'Достигнут лимит 8 активных наборов данных. Перезапустите локальный сервер или дождитесь истечения 2 часов.')
        key = uuid.uuid4().hex
        store[key] = {'df':df,'filename':(file.filename or 'transactions.csv')[:150],'analysis':None,'time':time.time()}
    return {'dataset_id':key,'transactions':len(df),'filename':store[key]['filename']}

@app.post('/api/analyze')
def analyze(entry=Depends(dataset)):
    with lock:
        if entry['analysis'] is None:
            entry['analysis'] = Analysis(entry['df'],entry['filename'])
    return entry['analysis'].payload()

@app.get('/api/graph')
def graph(a=Depends(analyzed)):
    return a.payload()

@app.get('/api/node/{node_id}')
def node(node_id:str,a=Depends(analyzed)):
    require_node(a,node_id)
    return a.nodes[node_id]

@app.get('/api/network/{node_id}/hops')
def hops(node_id:str,depth:int=Query(4,ge=1,le=4),direction:str=Query('both',pattern='^(both|incoming|outgoing)$'),a=Depends(analyzed)):
    require_node(a,node_id)
    distances = hop_nodes(a.graph,node_id,depth,direction)
    return {**a.payload(distances),'depth':depth,'direction':direction,'distances':distances}

@app.get('/api/investigation/ranking')
def ranking(a=Depends(analyzed)):
    return a.ranking

@app.get('/api/evidence/{node_id}')
def evidence(node_id:str,a=Depends(analyzed)):
    require_node(a,node_id)
    return a.evidence(node_id)

@app.post('/api/ai/explain-node')
def explain(body:NodeRequest,a=Depends(analyzed)):
    require_node(a,body.node_id)
    return {**ai_copilot.explain(a.context(body.node_id)),'evidence_node_ids':[body.node_id]}

@app.post('/api/ai/compare-nodes')
def compare(body:CompareRequest,a=Depends(analyzed)):
    for n in [body.node_a,body.node_b]:
        require_node(a,n)
    if body.node_a==body.node_b:
        raise HTTPException(422,'Выберите два разных счёта.')
    context = {'nodes':[a.nodes[body.node_a],a.nodes[body.node_b]],'evidence':[a.context(body.node_a),a.context(body.node_b)]}
    return {**ai_copilot.compare(context),'evidence_node_ids':[body.node_a,body.node_b],'nodes':context['nodes']}

@app.post('/api/ai/chat')
def chat(body:ChatRequest,a=Depends(analyzed)):
    require_node(a,body.node_id)
    mentioned = [n for n in a.nodes if n != body.node_id and re.search(r'(?<![\w])'+re.escape(n)+r'(?![\w])', body.question)][:2]
    context = {**a.context(body.node_id),'question':body.question,'related_nodes':[a.nodes[n] for n in mentioned]}
    return {**ai_copilot.chat(context),'evidence_node_ids':[body.node_id,*mentioned]}

@app.post('/api/ai/investigation-summary')
def summary(a=Depends(analyzed)):
    top = a.ranking[:5]
    ctx = {'stats':a.stats,'top_nodes':top,'pattern_counts':a.pattern_counts,'paths':[p for n in top[:3] for p in a.paths(n['node_id'],3)]}
    return {**ai_copilot.summary(ctx),'evidence_node_ids':[n['node_id'] for n in top]}

if (ROOT/'frontend/dist').exists():
    app.mount('/',StaticFiles(directory=ROOT/'frontend/dist',html=True),name='frontend')
