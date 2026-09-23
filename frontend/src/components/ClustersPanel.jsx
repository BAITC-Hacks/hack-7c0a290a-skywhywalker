import {roles,roleHints,roleColors} from '../services/labels';
import {fmt,amountUnit} from '../services/api';

function topIds(value) {
  if (Array.isArray(value)) return value.map(String);
  if (!value) return [];
  try { const parsed=JSON.parse(value); if(Array.isArray(parsed))return parsed.map(String); } catch { /* A comma-separated list is also supported. */ }
  return String(value).split(/[,;\s]+/).filter(Boolean);
}

export default function ClustersPanel({clusters,ranking,currency,onSelect}) {
  return <div className="clusters-panel">
    <p className="notice">Роль — гипотеза по наблюдаемым переводам. Все счета, включая изолированные, входят в выгрузку. Сходство роли с преступной схемой не устанавливает нарушение.</p>
    <div className="role-overview">{Object.entries(roles).map(([key,label])=><section key={key}><span className="role-dot" style={{background:roleColors[key]}}/><h3>{label}</h3><strong>{fmt(ranking.filter(n=>n.role===key).length)}</strong><p>{roleHints[key]}</p></section>)}</div>
    <h3>Группы связанных счетов · {clusters.length}</h3>
    <div className="table-scroll clusters-table"><table><thead><tr><th>Группа</th><th>Счетов</th><th>Исходных</th><th>Внутренний объём, {amountUnit(currency)}</th><th>Ключевые счета</th><th>Гипотеза</th></tr></thead><tbody>{clusters.map(cluster=><tr key={cluster.cluster_id}><td>{cluster.cluster_id}</td><td>{fmt(cluster.n_nodes)}</td><td>{fmt(cluster.n_seed)}</td><td>{fmt(cluster.sum_kzt_internal)}</td><td><div className="cluster-node-links">{topIds(cluster.top_gids).map(id=><button key={id} onClick={()=>onSelect(id)} title={`Открыть счёт ${id}`}>{id}</button>)}</div></td><td className="cluster-hypothesis">{cluster.hypothesis||'Гипотеза не задана'}</td></tr>)}</tbody></table></div>
    <p className="muted small">Крупнейшая группа не обязательно содержит наиболее приоритетный счёт. Проверьте роль, исходные переводы и границы выборки.</p>
  </div>;
}
