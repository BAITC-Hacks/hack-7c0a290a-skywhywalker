import {useEffect,useMemo,useRef,useState} from 'react';
import {Search,SlidersHorizontal,Network,ChevronRight,ShieldCheck,X,Sparkles,GitCompareArrows,FileSearch,AlertCircle,Layers,Database} from 'lucide-react';
import Sidebar from './components/Sidebar';
import StatsBar from './components/StatsBar';
import UploadPanel from './components/UploadPanel';
import MoneyGraph from './components/MoneyGraph';
import NodeDetails from './components/NodeDetails';
import AICopilot,{AIResult} from './components/AICopilot';
import EvidencePanel from './components/EvidencePanel';
import HelpPanel from './components/HelpPanel';
import ClustersPanel from './components/ClustersPanel';
import {api,setDataset,downloadExports,patternLabel,fmt,dateLabel} from './services/api';
import {levels,components,componentAvailable,roles,roleName} from './services/labels';

function Modal({title,onClose,children}) {
  const dialog=useRef();
  useEffect(()=>{const element=dialog.current;element.showModal();return()=>element.close();},[]);
  return <dialog ref={dialog} onCancel={onClose} onClick={event=>{if(event.target===dialog.current)onClose();}}><header className="modal-header"><h2>{title}</h2><button aria-label="Закрыть" onClick={onClose}><X size={20}/></button></header><div className="modal-body">{children}</div></dialog>;
}

export default function App() {
  const [graph,setGraph]=useState(null),[ranking,setRanking]=useState([]),[selected,setSelected]=useState(''),[node,setNode]=useState(null);
  const [datasets,setDatasets]=useState([]),[datasetId,setDatasetId]=useState('official'),[filename,setFilename]=useState(''),[pending,setPending]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [priority,setPriority]=useState('ALL'),[pattern,setPattern]=useState('ALL'),[role,setRole]=useState('ALL'),[colorMode,setColorMode]=useState('roles');
  const [minAmount,setMinAmount]=useState(''),[maxAmount,setMaxAmount]=useState(''),[depth,setDepth]=useState(4),[direction,setDirection]=useState('outgoing');
  const [following,setFollowing]=useState(false),[followIds,setFollowIds]=useState(null),[search,setSearch]=useState(''),[resetKey,setResetKey]=useState(0),[focusKey,setFocusKey]=useState(0);
  const [tab,setTab]=useState('details'),[explanation,setExplanation]=useState(null),[messages,setMessages]=useState([]),[modal,setModal]=useState(null);
  const [evidence,setEvidence]=useState(null),[comparison,setComparison]=useState(null),[compareId,setCompareId]=useState(''),[briefing,setBriefing]=useState(null),[clusters,setClusters]=useState([]);
  const epoch=useRef(0),currentNode=useRef(''),pendingActions=useRef(0);
  const rankingMap=useMemo(()=>new Map(ranking.map(item=>[item.node_id,item])),[ranking]);
  const sourceName=datasets.find(item=>item.id===datasetId)?.name||(datasetId==='official'?'Данные хакатона':datasetId==='demo'?'Учебный пример':'Загруженный файл');
  const patterns=useMemo(()=>[...new Set(ranking.flatMap(item=>item.patterns||[]))].sort(),[ranking]);

  async function run(action) {
    pendingActions.current++;setBusy(true);setError('');
    try{await action();}catch(err){setError(err.message||'Не удалось связаться с сервером приложения.');}
    finally{pendingActions.current--;setBusy(pendingActions.current>0);}
  }
  function resetView() {
    setPriority('ALL');setPattern('ALL');setRole('ALL');setMinAmount('');setMaxAmount('');setFollowing(false);setFollowIds(null);setResetKey(key=>key+1);
  }
  function select(id,list=ranking) {
    const identifier=String(id);
    currentNode.current=identifier;setSelected(identifier);setNode(list.find(item=>item.node_id===identifier)||null);setFocusKey(key=>key+1);
    setExplanation(null);setMessages([]);setTab('details');setError('');setPriority('ALL');setPattern('ALL');setRole('ALL');
  }
  function clearDataset() {
    setGraph(null);setRanking([]);setNode(null);setSelected('');currentNode.current='';setSearch('');setExplanation(null);setMessages([]);setClusters([]);setComparison(null);setBriefing(null);setEvidence(null);setModal(null);resetView();
  }
  async function loadGraph(version=epoch.current) {
    const [nextGraph,nextRanking]=await Promise.all([api('/graph'),api('/investigation/ranking')]);
    if(version!==epoch.current)return;
    const normalized=nextRanking.map(item=>({...item,node_id:String(item.node_id)}));
    setGraph(nextGraph);setRanking(normalized);setFilename(nextGraph.stats.filename);setPending(false);setSearch('');resetView();
    select(normalized[0]?.node_id||'',normalized);
  }
  async function changeDataset(id) {
    await run(async()=>{
      const version=++epoch.current;clearDataset();setDataset(id);setDatasetId(id);setPending(false);setNotice('');
      await loadGraph(version);
      if(version===epoch.current)setNotice(id==='demo'?'Открыт учебный пример: все счета и переводы вымышлены.':'Набор данных загружен. Изучите ограничения выборки перед выводами.');
    });
  }
  useEffect(()=>{
    run(async()=>{
      const available=await api('/datasets');
      setDatasets(available);
      const initial=available.find(item=>item.id==='official')||available[0];
      if(!initial)throw new Error('Нет доступных наборов. Загрузите CSV, Parquet или ZIP.');
      setDataset(initial.id);setDatasetId(initial.id);
      await loadGraph();
      if(initial.id==='demo')setNotice('Данные хакатона не установлены. Открыт вымышленный учебный пример; официальный ZIP можно загрузить кнопкой выше.');
    });
  },[]);
  useEffect(()=>{
    if(!selected)return;
    const controller=new AbortController(),version=epoch.current;
    api(`/node/${encodeURIComponent(selected)}`,undefined,{signal:controller.signal}).then(result=>{if(version===epoch.current)setNode(result);}).catch(err=>{if(err.name!=='AbortError'&&version===epoch.current)setError(err.message);});
    return()=>controller.abort();
  },[selected,graph]);
  useEffect(()=>{
    if(!following||!selected){setFollowIds(null);return;}
    const controller=new AbortController(),version=epoch.current;
    setFollowIds(null);
    api(`/network/${encodeURIComponent(selected)}/hops?depth=${depth}&direction=${direction}`,undefined,{signal:controller.signal}).then(result=>{if(version===epoch.current)setFollowIds(result.nodes.map(item=>String(item.data.id)));}).catch(err=>{if(err.name!=='AbortError'&&version===epoch.current)setError(err.message);});
    return()=>controller.abort();
  },[following,selected,depth,direction,graph]);
  async function upload(file) {
    await run(async()=>{
      const form=new FormData();form.append('file',file);
      const result=await api('/upload',form);
      epoch.current++;clearDataset();setDataset(result.dataset_id);setDatasetId(result.dataset_id);setFilename(result.filename||file.name);setPending(true);
      setNotice(`Файл проверен. Переводов: ${fmt(result.transactions)}. Нажмите «Построить граф».`);
    });
  }
  function analyze(){run(async()=>{const version=epoch.current;await api('/analyze',{});await loadGraph(version);if(version===epoch.current)setNotice('Готово. Рассчитаны граф, роли, группы и приоритеты. Выгрузки доступны в «Скачать 3 CSV».');});}
  function exportResults(){run(async()=>{await downloadExports();setNotice('Подготовлен ZIP: nodes_roles.csv, clusters.csv и top_nodes.csv.');});}
  function askExplain(){if(!selected)return;setTab('copilot');const id=selected,version=epoch.current;run(async()=>{const result=await api('/ai/explain-node',{node_id:id});if(version===epoch.current&&id===currentNode.current)setExplanation(result);});}
  function ask(question){const id=selected,version=epoch.current;run(async()=>{const result=await api('/ai/chat',{node_id:id,question});if(version===epoch.current&&id===currentNode.current)setMessages(previous=>[...previous,{question,result}]);});}
  function showEvidence(id=selected){const version=epoch.current;run(async()=>{const result=await api(`/evidence/${encodeURIComponent(id)}`);if(version===epoch.current){setEvidence(result);setModal('evidence');}});}
  function openCompare(){setComparison(null);setCompareId(ranking.find(item=>item.node_id!==selected)?.node_id||'');setModal('compare');}
  function compare(){const version=epoch.current;run(async()=>{const result=await api('/ai/compare-nodes',{node_a:selected,node_b:compareId});if(version===epoch.current)setComparison(result);});}
  function summary(){const version=epoch.current;run(async()=>{const result=await api('/ai/investigation-summary',{});if(version===epoch.current){setBriefing(result);setModal('summary');}});}
  function showClusters(){const version=epoch.current;run(async()=>{const result=await api('/clusters');if(version===epoch.current){setClusters(result);setModal('clusters');}});}
  function find(event){event.preventDefault();const identifier=search.trim();const match=rankingMap.has(identifier)?identifier:ranking.find(item=>item.node_id.toLowerCase()===identifier.toLowerCase())?.node_id;if(match){resetView();select(match);}else setError('Счёт не найден. Введите его полный идентификатор; поиск охватывает весь набор.');}
  function selectFromModal(id){if(!rankingMap.has(String(id))){setError('Счёт не найден в текущем наборе.');return;}setModal(null);resetView();select(String(id));}

  const actionRef=useRef({});actionRef.current={rankingMap,select,resetView};
  useEffect(()=>{
    const context=document.modelContext;if(!context?.registerTool)return;
    const lifecycle=new AbortController();
    try{Promise.resolve(context.registerTool({name:'select_moneygraph_account',description:'Выбрать существующий счёт в текущем наборе и открыть карточку проверки.',inputSchema:{type:'object',properties:{account_id:{type:'string'}},required:['account_id'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:true},async execute(input){if(!input||typeof input.account_id!=='string'||!actionRef.current.rankingMap.has(input.account_id))throw new Error('Счёт не найден');actionRef.current.resetView();actionRef.current.select(input.account_id);await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));return {selected_account:input.account_id};}},{signal:lifecycle.signal})).catch(()=>{});}catch{/* Optional browser integration. */}
    return()=>lifecycle.abort();
  },[]);

  return <div className="app-shell">
    <Sidebar ranking={ranking} selected={selected} onSelect={select} onSummary={summary} onClusters={showClusters} onHelp={()=>setModal('help')} busy={busy} filename={filename} sourceName={sourceName}/>
    <main className="main">
      <header className="topbar"><div><div className="breadcrumb">Рабочее пространство <ChevronRight size={13}/> Анализ переводов</div><h1>Деньги. Связи. Объяснения.<span className="header-ai">ИИ</span></h1><p className="page-subtitle">Роли участников, группы счетов и объяснимая очередь проверки.</p></div><UploadPanel busy={busy} onUpload={upload} onAnalyze={analyze} onExport={exportResults} hasGraph={Boolean(graph)}/></header>
      <div className="dataset-bar"><label><Database size={17}/><span>Набор данных</span><select aria-label="Выбрать набор данных" value={datasetId} onChange={event=>changeDataset(event.target.value)} disabled={busy}>{datasets.map(item=><option key={item.id} value={item.id}>{item.id==='official'?'Данные хакатона':item.id==='demo'?'Учебный пример':item.name}</option>)}{!datasets.some(item=>item.id===datasetId)&&<option value={datasetId}>{sourceName}</option>}</select></label><button onClick={showClusters} disabled={busy||!graph}><Layers size={16}/>Роли и группы</button></div>
      <div className="getting-started"><div><b>Начните с карты переводов</b><span>Круг — счёт. Стрелка — перевод. Цвет — выбранная роль, группа или приоритет.</span></div><button onClick={()=>setModal('help')}>Как пользоваться <ChevronRight size={16}/></button></div>
      <StatsBar stats={graph?.stats}/>
      {graph&&<div className="dataset-context"><span>{graph.stats.time_precision==='day'?'Точность: дата, без времени суток':'Временные интервалы: по данным файла'}</span><span>Без связей: {fmt(graph.stats.isolated_count)}</span><span>На границе обхода: {fmt(graph.stats.boundary_count)}</span>{datasetId==='demo'&&<b>Все данные вымышлены</b>}</div>}
      {!!graph?.stats.warnings?.length&&<details className="dataset-warnings"><summary>Ограничения выборки · {graph.stats.warnings.length}</summary><ul>{graph.stats.warnings.map((warning,index)=><li key={index}>{warning}</li>)}</ul></details>}
      {error&&<div role="alert" className="error-banner"><AlertCircle size={18}/>{error}<button aria-label="Закрыть ошибку" onClick={()=>setError('')}><X size={16}/></button></div>}
      {notice&&<div role="status" className="notice-banner">{notice}<button aria-label="Закрыть уведомление" onClick={()=>setNotice('')}><X size={15}/></button></div>}
      <div className="workspace">
        <section className="graph-panel">
          <div className="graph-header"><div><h2 id="graph-heading"><Network size={18}/>Граф переводов</h2><p>{graph?`${dateLabel(graph.stats.start,'day')} — ${dateLabel(graph.stats.end,'day')}${graph.stats.time_precision==='day'?'':' · UTC'}`:'Загрузите CSV, Parquet или ZIP'}</p></div><div className="graph-header-actions"><button className="text-button" onClick={summary} disabled={busy||!graph}><Sparkles size={14}/>Сводка от ИИ</button><button className="text-button" onClick={resetView}>Сбросить вид</button></div></div>
          <div className="graph-toolbar"><form className="search" onSubmit={find}><Search size={16}/><input aria-label="Полный идентификатор счёта" placeholder="Полный идентификатор счёта" value={search} onChange={event=>setSearch(event.target.value)}/><button aria-label="Найти счёт во всём наборе" type="submit">↵</button></form><div className="depth-control"><span title="1 — прямые соседи; 4 — связи на расстоянии до четырёх переводов.">Переходов</span>{[1,2,3,4].map(value=><button key={value} className={depth===value?'active':''} disabled={!selected} onClick={()=>{setDepth(value);setFollowing(true);}} aria-pressed={depth===value}>{value}</button>)}</div></div>
          <div className="filter-bar"><SlidersHorizontal size={15}/><select aria-label="Фильтр по приоритету" value={priority} onChange={event=>setPriority(event.target.value)}>{Object.entries(levels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><select aria-label="Фильтр по роли" value={role} onChange={event=>setRole(event.target.value)}><option value="ALL">Все роли</option>{Object.entries(roles).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><select aria-label="Фильтр по особенностям" value={pattern} onChange={event=>setPattern(event.target.value)}><option value="ALL">Все особенности</option>{patterns.map(value=><option key={value} value={value}>{patternLabel(value)}</option>)}</select><input type="number" min="0" aria-label="Минимальная сумма отдельного перевода" placeholder="Сумма от" value={minAmount} onChange={event=>setMinAmount(event.target.value)}/><span>–</span><input type="number" min="0" aria-label="Максимальная сумма отдельного перевода" placeholder="Сумма до" value={maxAmount} onChange={event=>setMaxAmount(event.target.value)}/><select aria-label="Цвет счетов на графе" value={colorMode} onChange={event=>setColorMode(event.target.value)}><option value="roles">Цвет: роли</option><option value="priority">Цвет: приоритет</option><option value="communities">Цвет: группы</option></select></div>
          {Number(minAmount)>Number(maxAmount)&&maxAmount!==''&&<p className="notice">Минимальная сумма больше максимальной: переводы скрыты.</p>}
          {following&&<div className="follow-banner"><span>СВЯЗИ СЧЁТА <b>{selected}</b> · переходов: {depth} · счетов: {followIds?.length??'…'}</span><select aria-label="Направление переводов" value={direction} onChange={event=>setDirection(event.target.value)}><option value="outgoing">По исходящим</option><option value="incoming">По входящим</option><option value="both">Все связи</option></select><button aria-label="Показать всю сеть" onClick={resetView}><X size={15}/></button></div>}
          {graph?<MoneyGraph graph={graph} selected={selected} onSelect={select} priority={priority} pattern={pattern} role={role} minAmount={minAmount} maxAmount={maxAmount} followIds={followIds} resetKey={resetKey} focusKey={focusKey} colorMode={colorMode}/>:<div className="empty-graph"><Network size={48}/><h2>{pending?'Файл готов к анализу':'Карта денежных переводов'}</h2><p>{busy?'Обрабатываем данные…':pending?'Нажмите «Построить граф», чтобы увидеть связи.':'Загрузите файл или выберите доступный набор данных.'}</p>{datasets.some(item=>item.id==='demo')&&<button onClick={()=>changeDataset('demo')} disabled={busy}>Открыть учебный пример</button>}</div>}
          <div className="graph-footer"><ShieldCheck size={15}/><span>Роли и приоритеты — гипотезы для проверки, не доказательство нарушения.</span></div>
        </section>
        <aside className="detail-panel"><div className="panel-tabs"><button className={tab==='details'?'active':''} onClick={()=>setTab('details')}><FileSearch size={16}/>О счёте</button><button className={tab==='copilot'?'active':''} onClick={()=>setTab('copilot')}><Sparkles size={16}/>ИИ-помощник</button></div><div className="detail-content">{tab==='details'?<NodeDetails node={node} metadata={graph?.stats} onFollow={()=>following?resetView():setFollowing(true)} onAI={askExplain} onEvidence={()=>showEvidence()} onCompare={openCompare} following={following} busy={busy}/>:<AICopilot node={node} result={explanation} messages={messages} onExplain={askExplain} onAsk={ask} onEvidence={showEvidence} busy={busy}/>}</div></aside>
      </div>
      <footer className="page-footer"><span>MoneyGraph <b>/</b> Аналитический прототип</span><span>{busy?'Обработка…':sourceName} · Оценки в CSV: 0–1</span></footer>
    </main>
    {modal==='help'&&<Modal title="Как работает MoneyGraph" onClose={()=>setModal(null)}><HelpPanel/></Modal>}
    {modal==='clusters'&&<Modal title="Роли и группы" onClose={()=>setModal(null)}><ClustersPanel clusters={clusters} ranking={ranking} currency={graph?.stats.currency} onSelect={selectFromModal}/></Modal>}
    {modal==='evidence'&&<Modal title={`Основания оценки · ${evidence?.node_id}`} onClose={()=>setModal(null)}><EvidencePanel evidence={evidence}/></Modal>}
    {modal==='compare'&&<Modal title="Сравнение счетов" onClose={()=>setModal(null)}><div className="compare-picker"><b>{selected}</b><span>и</span><select aria-label="Счёт для сравнения" value={compareId} onChange={event=>{setCompareId(event.target.value);setComparison(null);}}>{ranking.filter(item=>item.node_id!==selected).map(item=><option key={item.node_id} value={item.node_id}>{item.node_id}</option>)}</select><button className="primary" disabled={!compareId||busy} onClick={compare}><GitCompareArrows size={16}/>Сравнить</button></div>{comparison&&<><div className="compare-grid">{comparison.nodes.map(item=><div key={item.node_id}><h3>{item.node_id} <span className={item.priority_level.toLowerCase()}>{fmt(item.priority_score)}</span></h3><p>{roleName(item.role)}</p>{Object.entries(item.components).map(([key,value])=><p className="row-between" key={key}><span>{components[key]||key}</span><b>{componentAvailable(item,key)?fmt(value):'Нет данных'}</b></p>)}<button onClick={()=>showEvidence(item.node_id)}>Основания</button></div>)}</div><AIResult result={comparison} onEvidence={showEvidence}/></>}</Modal>}
    {modal==='summary'&&briefing&&<Modal title="Сводка по сети" onClose={()=>setModal(null)}><div className="ai-mode"><Sparkles size={16}/>{briefing.mode==='openai'?'ОТВЕТ ИИ · OPENAI':'СВОДКА ПО ПРАВИЛАМ'}</div><p className="notice">{briefing.notice}</p>{[['Обзор сети',briefing.network_overview],['Какие счета изучить',briefing.key_nodes],['Особенности переводов',briefing.detected_patterns],['Цепочки переводов',briefing.important_transaction_paths],['Что проверить дальше',briefing.suggested_investigation_areas],['Ограничения выводов',briefing.limitations]].map(([title,value])=><section className="briefing-section" key={title}><h3>{title}</h3>{Array.isArray(value)?<ul>{value.map((text,index)=><li key={index}>{text}</li>)}</ul>:<p>{value}</p>}</section>)}<div className="evidence-links">{(briefing.evidence_node_ids||[]).map(id=><button key={id} onClick={()=>showEvidence(id)}>Основания · {id}</button>)}</div></Modal>}
  </div>;
}
