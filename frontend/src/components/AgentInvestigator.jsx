import {useState} from 'react';
import {Sparkles,ArrowRight,ShieldCheck,FileSearch,RotateCcw,LoaderCircle} from 'lucide-react';
import AgentActivity from './ui/AgentActivity';

export default function AgentInvestigator({node,result,running,busy,onRun,onEvidence,onSelect}) {
  const [question,setQuestion]=useState('');
  return <div className="investigator">
    <div className="investigator-heading"><span className="agent-symbol"><Sparkles size={22}/></span><div><span className="eyebrow">ОГРАНИЧЕННЫЙ AI-АГЕНТ</span><h3>От сигнала — к проверке</h3></div></div>
    {node&&<p className="agent-selected-account">Выбранный счёт <b>{node.node_id}</b></p>}
    <p className="agent-intro">Сам выбирает, какие сведения о счёте, связях и операциях запросить. Затем предлагает следующий шаг с основаниями.</p>
    <details className={`agent-task-form ${result&&!running?'has-result':''}`} open={!result||running}><summary>Настроить и повторить проверку</summary><form onSubmit={event=>{event.preventDefault();onRun(question);}}>
      <label htmlFor="agent-question">Задача для выбранного счёта</label>
      <textarea id="agent-question" value={question} onChange={event=>setQuestion(event.target.value)} maxLength={1000} placeholder="Почему этот счёт важен и кого проверить следующим?" rows={2} disabled={running}/>
      <button className="primary agent-run" disabled={!node||busy||running} type="submit">{running?<LoaderCircle size={16} className="spin"/>:result?<RotateCcw size={16}/>:<Sparkles size={16}/>} {running?'Исследование выполняется…':result?'Повторить проверку':'Запустить AI-проверку'}</button>
    </form>
    <p className="agent-boundary"><ShieldCheck size={13}/>Только чтение · до 5 вызовов инструментов · без изменения оценок</p>
    <p className="agent-disclosure">При запуске ограниченные сведения о счетах и переводах передаются в OpenAI.</p></details>
    {!result&&!running&&<div className="agent-placeholder"><b>Что вы получите</b><p>Проверенные факты, журнал запросов к данным и следующий счёт для ручной проверки.</p><span>1. Сведения о счёте → 2. Связи и операции → 3. Следующий шаг</span></div>}
    {(running||result)&&<AgentActivity key={running?'running':'result'} items={running?[]:result?.trace||[]} working={running} defaultOpen={running||result?.status!=='completed'}/>}
    {result&&!running&&<div className="agent-report" aria-live="polite">
      <div className={`agent-result-status ${result.mode!=='agent'?'rules':''}`}><span className="live-dot"/>{result.mode==='agent'?(result.status==='completed'?'Проверка агентом завершена':'Проверка агентом ограничена'):'Сводка по правилам · не агент'}</div>
      <p className="agent-notice">{result.notice}</p>
      <h4>Результат проверки</h4><p className="agent-summary">{result.summary}</p>
      <div className="agent-findings">{result.findings?.map((finding,index)=><article key={index}><span className="finding-index">{index+1}</span><div><p>{finding.text}</p><div className="finding-links">{finding.node_ids.map(id=><button key={id} onClick={()=>onEvidence(id)} title={`Основания счёта ${id}`}><FileSearch size={12}/>{id.length>12?`…${id.slice(-9)}`:id}</button>)}</div>{!!finding.transaction_ids.length&&<small>Операции: {finding.transaction_ids.join(', ')}</small>}</div></article>)}</div>
      {result.next_node_id&&<button className="next-candidate" onClick={()=>onSelect(result.next_node_id)}><span><small>Следующий счёт для проверки</small><b>{result.next_node_id}</b></span><ArrowRight size={20}/></button>}
      {!!result.suggested_checks?.length&&<section className="agent-next-checks"><h4>Что проверить аналитику</h4><ul>{result.suggested_checks.map((check,index)=><li key={index}>{check}</li>)}</ul></section>}
      <p className="limitations">{result.limitations}</p>
    </div>}
  </div>;
}
