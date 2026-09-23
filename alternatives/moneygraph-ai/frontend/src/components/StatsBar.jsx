import {Users, ArrowLeftRight, Layers, ScanLine, GitBranch, Coins} from 'lucide-react';
import {short,fmt} from '../services/api';
export default function StatsBar({stats}){
 const items=[['Accounts',stats?.accounts,Users],['Transactions',stats?.transactions,ArrowLeftRight],['Total volume',short(stats?.total_volume),Coins],['Communities',stats?.communities,Layers],['High priority',stats?.high_priority,ScanLine],['Patterns',stats?.detected_patterns,GitBranch]];
 return <div className="stats">{items.map(([label,value,Icon])=><div className="stat" key={label}><span><Icon size={15}/>{label}</span><strong className={label==='High priority'&&value?'high':''}>{value??'—'}</strong>{label==='Total volume'&&<small title={fmt(stats?.total_volume)}>единицы dataset</small>}</div>)}</div>
}
