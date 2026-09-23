import {Users,ArrowLeftRight,Layers,ScanLine,GitBranch,Coins} from 'lucide-react';
import {short,fmt,amountUnit} from '../services/api';

export default function StatsBar({stats}) {
  const items=[['Счетов',stats?.accounts,Users],['Переводов',stats?.transactions,ArrowLeftRight],['Общий объём',stats?short(stats.total_volume):undefined,Coins],['Групп счетов',stats?.communities,Layers],['Высокий приоритет',stats?.high_priority,ScanLine],['Исходных счетов',stats?.seed_count,GitBranch]];
  return <div className="stats">{items.map(([label,value,Icon])=><div className="stat" key={label}><span><Icon size={16}/>{label}</span><strong className={label==='Высокий приоритет'&&value?'high':''}>{value??'—'}</strong>{label==='Общий объём'&&<small title={stats?fmt(stats.total_volume):undefined}>{amountUnit(stats?.currency)}</small>}</div>)}</div>;
}
