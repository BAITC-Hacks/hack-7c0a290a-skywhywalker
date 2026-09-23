// Adapted from starc007 / beui.dev Agent Activity, retrieved through 21st MCP.
// https://21st.dev/@starc007/components/agent-activity
// Keeps controlled disclosure and activity-list semantics. No demo events,
// simulated reasoning, media, motion dependency or private model thoughts.
import {useCallback,useId,useState} from 'react';
import {Check,ChevronDown,Database,LoaderCircle,AlertCircle} from 'lucide-react';

function useControllableOpen({open,defaultOpen,onOpenChange}) {
  const [internalOpen,setInternalOpen]=useState(defaultOpen);
  const controlled=open!==undefined;
  const setOpen=useCallback(next=>{if(!controlled)setInternalOpen(next);onOpenChange?.(next);},[controlled,onOpenChange]);
  return [open??internalOpen,setOpen];
}

export default function AgentActivity({items=[],working=false,open,defaultOpen=true,onOpenChange}) {
  const baseId=useId();
  const [expanded,setOpen]=useControllableOpen({open,defaultOpen,onOpenChange});
  return <section className="agent-activity" aria-busy={working}>
    <button className="activity-toggle" id={`${baseId}-trigger`} aria-expanded={expanded} aria-controls={`${baseId}-content`} onClick={()=>setOpen(!expanded)}>
      <span><Database size={15}/>Журнал действий <b>{items.length}</b></span><ChevronDown size={15} className={expanded?'rotated':''}/>
    </button>
    {working&&<p className="agent-working" role="status"><LoaderCircle size={16} className="spin"/>Агент выбирает инструменты и проверяет данные. Журнал появится после ответа сервера.</p>}
    {expanded&&<div id={`${baseId}-content`} role="region" aria-labelledby={`${baseId}-trigger`}>
      {!!items.length&&<ol className="activity-list">{items.map((item,index)=><li key={`${item.step}-${index}`}>
        <span className={`activity-marker ${item.status!=='ok'?'failed':''}`} aria-hidden="true">{item.status!=='ok'?<AlertCircle size={13}/>:<Check size={13}/>}</span>
        <div><div className="activity-heading"><b>{item.title}</b><span>{String(item.step).padStart(2,'0')}</span></div><small className="activity-node">Счёт {item.node_id}</small><p>{item.summary}</p><code>{item.tool}</code></div>
      </li>)}</ol>}
      {!working&&!items.length&&<p className="activity-empty">Нет выполненных вызовов инструментов. Сводка по правилам не выдаётся за работу агента.</p>}
    </div>}
  </section>;
}
