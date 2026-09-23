import {Network,ListOrdered,ShieldCheck,Sparkles,Database,ArrowUpRight,CircleHelp,Layers} from 'lucide-react';
import InvestigationList from './InvestigationList';

export default function Sidebar({ranking,selected,onSelect,onSummary,onClusters,onHelp,busy,filename,sourceName}) {
  return <aside className="sidebar">
    <a className="brand" href="#" aria-label="MoneyGraph"><span className="brand-icon"><Network size={26}/></span><span>MoneyGraph<small>Анализ переводов с ИИ</small></span></a>
    <div className="workspace-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
    <nav>
      <button className="nav-item active" onClick={()=>document.getElementById('graph-heading')?.scrollIntoView({behavior:'smooth'})}><Network size={18}/>Граф переводов</button>
      <button className="nav-item" onClick={()=>document.getElementById('ranking')?.focus()}><ListOrdered size={18}/>Очередь проверки</button>
      <button className="nav-item" onClick={onClusters} disabled={busy||!ranking.length}><Layers size={18}/>Роли и группы</button>
      <button className="nav-item" onClick={onSummary} disabled={busy||!ranking.length}><Sparkles size={18}/>Сводка от ИИ<ArrowUpRight size={14}/></button>
      <button className="nav-item" onClick={onHelp}><CircleHelp size={18}/>Как это работает</button>
    </nav>
    <InvestigationList ranking={ranking} selected={selected} onSelect={onSelect}/>
    <div className="sidebar-bottom"><div className="source-label"><Database size={16}/> ИСТОЧНИК ДАННЫХ</div><p>{sourceName}</p><p title={filename}>{filename||'Файл не выбран'}</p><div className="local-note"><ShieldCheck size={18}/><span>Гипотезы для проверки<br/><small>Решение принимает аналитик</small></span></div></div>
  </aside>;
}
