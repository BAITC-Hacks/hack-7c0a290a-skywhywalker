import {fmt,amountUnit,dateLabel} from '../services/api';
import {components,componentAvailable,componentWeight,patternName,metricName,percentMetrics,rules,observedText,roleName} from '../services/labels';

const minuteMetrics=new Set(['matched_amount','rapid_amount','rapid_share','average_holding_minutes']);
export default function EvidencePanel({evidence}) {
  if(!evidence)return null;
  const metadata=evidence.metadata||{};
  const day=metadata.time_precision==='day';
  const pairs=evidence.metrics.rapid_pairs||[];
  const fast=evidence.metrics.fast_forward_fraction??evidence.node?.fast_forward_fraction;
  const valueText=(key,value)=>value==null?'Нет данных':typeof value==='boolean'?(value?'Да':'Нет'):key==='role'?roleName(value):typeof value==='number'?(percentMetrics.has(key)?`${fmt(value*100)}%`:new Intl.NumberFormat('ru-RU',{maximumFractionDigits:4}).format(value)):String(value);
  return <div className="evidence">
    <p className="notice">Исходные переводы, рассчитанные показатели и сработавшие правила. Суммы: {metadata.currency==='KZT'?'тенге (KZT)':'единицы исходного файла; валюта не указана'}.</p>
    {day&&<p className="data-warning">В исходных данных известны только даты. Порядок операций внутри дня и интервалы в минутах неизвестны.</p>}
    {(metadata.warnings||[]).map((warning,index)=><p className="muted small" key={index}>{warning}</p>)}
    <h3>Показатели счёта {evidence.node_id}</h3>
    <dl className="evidence-metrics">{Object.entries(evidence.metrics).filter(([key])=>key!=='rapid_pairs'&&(!day||!minuteMetrics.has(key))).map(([key,value])=><div key={key}><dt>{metricName(key)}</dt><dd>{valueText(key,value)}</dd></div>)}</dl>
    <h3>Почему сработали правила</h3>
    {evidence.rules.length?evidence.rules.map(rule=><div className="rule" key={rule.pattern}><b>{patternName(rule.pattern)}</b><p>{day&&['RAPID_PASS_THROUGH','POTENTIAL_MULE_PATTERN'].includes(rule.pattern)?'Признак по доступным датам; минутная последовательность не установлена.':rules[rule.pattern]||'Правило анализа сети'}</p><div className="observed"><strong>В данных: </strong>{observedText(rule.observed)}</div></div>):<p className="muted">Заданные признаки не обнаружены.</p>}
    <h3>Цепочки переводов</h3><p className="muted small">До 8 путей через выбранный счёт. Реальные связи не доказывают, что по всей цепочке прошли одни и те же деньги.</p>
    {evidence.paths.length?evidence.paths.map((path,index)=><div className="path-card" key={index}><b>{path.nodes.join(' → ')}</b><span>{path.chronological?(day?'Каждая следующая операция датирована более поздним днём':'Переводы идут последовательно по времени'):(day?'Структурные связи; последовательность по разным дням не установлена':'Показаны связи; последовательность по времени не найдена')}</span><small>Номера переводов: {path.transaction_ids.join(' / ')}</small></div>):<p>Подходящих цепочек нет.</p>}
    {day?<><h3>Близкие поступления и отправления</h3><p>Индикатор в пределах 0–2 календарных дней: <b>{fast==null?'нет данных':`${fmt(fast*100)}%`}</b>. Это доля входящих операций, рядом с которыми есть исходящая в тот же или следующие два календарных дня. Суммы не сопоставляются. Внутри одного дня неизвестно, что произошло раньше; движение одних и тех же денег не установлено.</p></>:<><h3>Поступления и переводы дальше за один час</h3><p className="muted small">Сначала сопоставляются более ранние поступления. До 20 пар; расчётное предположение не доказывает движение конкретных денег.</p>{pairs.length?pairs.map((pair,index)=><div className="path-card" key={index}><b>{pair.incoming_transaction} → {pair.outgoing_transaction}</b><span>{fmt(pair.allocated_amount)} {amountUnit(metadata.currency)} · через {fmt(pair.minutes)} мин.</span></div>):<p>Сопоставленные пары не найдены или временной показатель недоступен.</p>}</>}
    <h3>Исходные переводы ({evidence.transaction_count})</h3>{evidence.transactions_truncated&&<p>Показаны первые 500 строк.</p>}
    <div className="table-scroll"><table><thead><tr><th>Номер</th><th>Отправитель</th><th>Получатель</th><th>Сумма, {amountUnit(metadata.currency)}</th><th>{day?'Дата':'Дата и время (UTC)'}</th></tr></thead><tbody>{evidence.transactions.map(tx=><tr key={tx.id}><td>{tx.id}</td><td>{tx.source}</td><td>{tx.target}</td><td>{fmt(tx.amount)}</td><td>{dateLabel(tx.timestamp??tx.date,metadata.time_precision)}</td></tr>)}</tbody></table></div>
    <h3>Как рассчитывается оценка</h3><p>Веса доступных компонентов: {Object.keys(components).filter(key=>componentAvailable(evidence,key)).map(key=>`${components[key]} — ${Math.round(componentWeight(evidence,key))}%`).join('; ')}. Недоступные компоненты исключаются, остальные веса пересчитываются.</p>{Object.keys(components).some(key=>!componentAvailable(evidence,key))&&<p className="muted">Нет данных: {Object.keys(components).filter(key=>!componentAvailable(evidence,key)).map(key=>components[key]).join(', ')}.</p>}<p>Затем применяется поправка на неполноту данных: ×{fmt(evidence.priority_multiplier??1)}. В интерфейсе приоритет — от 0 до 100; в CSV — от 0 до 1.</p><p className="muted">Группы выделяются по связям, необычность оценивается относительно загруженных счетов. Это объяснимые аналитические гипотезы, а не установленные роли в преступной группе.</p>
  </div>;
}
