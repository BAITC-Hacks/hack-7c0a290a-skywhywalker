import {Users,ArrowLeftRight,Layers,ListOrdered,Coins} from 'lucide-react';
import {short,fmt,amountUnit} from '../services/api';
import {StatsCard} from './ui/StatsCard';

export default function StatsBar({stats,ranking=[]}) {
  const candidates=ranking.filter(node=>!node.is_seed).length;
  const items=[
    ['Счетов в сети',stats?fmt(stats.accounts):'—',Users,stats?`${fmt(stats.seed_count)} исходных клиентов`:'Ожидаем данные'],
    ['Переводов',stats?fmt(stats.transactions):'—',ArrowLeftRight,'Исходные операции'],
    ['Объём переводов',stats?short(stats.total_volume):'—',Coins,amountUnit(stats?.currency)],
    ['Групп связей',stats?fmt(stats.communities):'—',Layers,'Структурные гипотезы'],
    ['Кандидатов в выгрузке',stats?Math.min(50,candidates):'—',ListOrdered,'По приоритету, без исходных',true],
  ];
  return <div className="metric-grid">{items.map(([title,value,Icon,description,accent])=><StatsCard key={title} title={title} value={value} icon={<Icon size={17}/>} description={description} accent={accent}/>)}</div>;
}
