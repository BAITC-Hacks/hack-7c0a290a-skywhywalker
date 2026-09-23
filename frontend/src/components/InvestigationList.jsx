import {roleName,levels} from '../services/labels';
import {fmt} from '../services/api';

export default function InvestigationList({ranking,selected,onSelect}) {
  const firstHundred = ranking.slice(0,100);
  const selectedOutside = ranking.find(n=>n.node_id===selected && !firstHundred.some(v=>v.node_id===selected));
  const visible = selectedOutside ? [selectedOutside,...firstHundred.slice(0,99)] : firstHundred;
  const row = (node,index,extra=false) => <button key={node.node_id} className={`rank-row ${selected===node.node_id?'selected':''}`} onClick={()=>onSelect(node.node_id)} aria-label={`Счёт ${node.node_id}, приоритет ${fmt(node.priority_score)}`}>
    <span className="rank-number">{extra?'↗':String(index+1).padStart(2,'0')}</span>
    <span className="rank-account"><b title={node.node_id}>{node.node_id}</b><small>{roleName(node.role)}</small></span>
    <span title={`${levels[node.priority_level]} приоритет`} className={`score ${node.priority_level.toLowerCase()}`}>{fmt(node.priority_score)}</span>
  </button>;
  return <section id="ranking" className="ranking" tabIndex={-1}>
    <div className="section-label">ОЧЕРЕДЬ ПРОВЕРКИ <span>{ranking.length}</span></div>
    <p className="muted small">{ranking.length>100?`${selectedOutside?'99 первых и выбранный счёт':'Первые 100'} из ${fmt(ranking.length)}. Поиск по полному идентификатору — во всём наборе.`:'Чем выше балл, тем раньше стоит изучить счёт.'}</p>
    <div className="ranking-scroll">{visible.map((node,index)=>row(node,selectedOutside?index-1:index,Boolean(selectedOutside&&index===0)))}</div>
  </section>;
}
