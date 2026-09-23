export const levels = {ALL:'Все приоритеты',HIGH:'Высокий',MEDIUM:'Средний',LOW:'Низкий'};
export const components = {graph_score:'Связи в сети',anomaly_score:'Необычность',pattern_score:'Схемы переводов',flow_score:'Движение денег'};
export const componentWeights = {graph_score:35,anomaly_score:25,pattern_score:25,flow_score:15};
export const componentAvailable = (source,key) => source?.component_availability?.[key] !== false && source?.component_availability?.[key.replace('_score','')] !== false;
export const componentWeight = (source,key) => {
 const raw=source?.score_weights?.[key] ?? source?.score_weights?.[key.replace('_score','')];
 return typeof raw==='number' ? raw*100 : componentWeights[key];
};
export const roles = {consolidator:'Сбор средств',transit:'Транзит',distributor:'Распределение',terminal:'Возможный конечный получатель',coordinator:'Связующий узел',peripheral:'Периферия'};
export const roleHints = {
 consolidator:'Получает средства от нескольких участников; возможная точка консолидации.',
 transit:'Видимые поступления и отправления указывают на возможный транзит.',
 distributor:'Направляет переводы нескольким получателям.',
 terminal:'В видимой части сети получает средства и мало отправляет дальше. Полный баланс неизвестен.',
 coordinator:'Связывает участников и участки сети. Это структурная гипотеза, не вывод об организаторе.',
 peripheral:'Выбранные правила не выявили выраженную роль; отсутствие признаков не исключает нарушений.'
};
export const roleColors = {consolidator:'#4d9953',transit:'#478dae',distributor:'#ac843f',terminal:'#95649f',coordinator:'#c25a69',peripheral:'#9ca895'};
export const roleName = key => roles[key] || 'Роль не определена';
export const patterns = {
  COLLECTOR:['Сбор средств','На счёт поступают деньги как минимум от пяти разных отправителей.'],
  FAN_IN:['Много отправителей','Несколько входящих потоков сходятся в одном счёте.'],
  DISTRIBUTOR:['Распределение средств','Счёт отправляет деньги как минимум пяти разным получателям.'],
  FAN_OUT:['Много получателей','Счёт переводит деньги пяти или более разным получателям.'],
  CONSOLIDATOR:['Объединение потоков','На счёте сходятся как минимум две ветви, каждая — с несколькими источниками.'],
  BRIDGE:['Связь между группами','Счёт соединяет разные группы и часто находится на путях между другими счетами.'],
  RAPID_PASS_THROUGH:['Быстрый перевод дальше','Расчётный признак близких поступлений и отправлений; доступный интервал зависит от точности дат.'],
  POTENTIAL_MULE_PATTERN:['Возможный посреднический счёт','Совпали четыре признака: много отправителей, быстрый перевод дальше, высокий оборот и несколько получателей. Это повод изучить контекст, а не вывод о владельце.']
};
export const patternName = key => patterns[key]?.[0] || key;
export const patternHint = key => patterns[key]?.[1] || '';
export const metrics = {
 incoming_transaction_count:'Входящих переводов',outgoing_transaction_count:'Исходящих переводов',transaction_count:'Всего переводов',
 incoming_counterparties:'Разных отправителей',outgoing_counterparties:'Разных получателей',total_incoming_amount:'Сумма поступлений',total_outgoing_amount:'Сумма отправлений',
 total_volume:'Общий объём переводов',in_out_ratio:'Поступления / отправления',turnover_ratio:'Доля оборота',degree_centrality:'Доля связей в сети',in_degree:'Входящих связей',out_degree:'Исходящих связей',
 betweenness:'Роль посредника в сети',pagerank:'Значимость счёта в сети',community_id:'Номер группы',average_incoming_amount:'Средний входящий перевод',average_outgoing_amount:'Средний исходящий перевод',median_amount:'Медианная сумма перевода',communities_connected:'Связанных групп',matched_amount:'Сопоставленная сумма',rapid_amount:'Сумма быстрых переводов',rapid_share:'Доля быстрых переводов',average_holding_minutes:'Среднее время до перевода, мин.',
 communities:'Связанных групп',turnover:'Доля оборота',multiple_sources:'Несколько отправителей',rapid_forwarding:'Быстрый перевод дальше',high_turnover:'Высокий оборот',fan_in_fan_out:'Несколько отправителей и получателей',
 is_seed:'Исходный счёт',depth:'Глубина обхода',seed_reach:'Достигающих счёт исходных счетов',fast_forward_fraction:'Индикатор переводов в пределах 0–2 дней',truncated_by_depth:'Граница обхода',priority_multiplier:'Поправка приоритета',role_score:'Соответствие роли',role:'Предполагаемая роль',role_evidence:'Основание роли',cluster_id:'Номер группы',pass_through:'Отправлено / получено',in_deg:'Разных отправителей',out_deg:'Разных получателей',in_kzt:'Видимые поступления',out_kzt:'Видимые отправления',in_tx:'Входящих переводов',out_tx:'Исходящих переводов',retention_ratio:'Доля превышения поступлений над отправлениями',pass_through_ratio:'Отправлено / получено (в выборке)',timing_available:'Есть точное время операций'
};
export const metricName = key => metrics[key] || components[key] || key;
export const percentMetrics = new Set(['rapid_share','turnover_ratio','turnover','fast_forward_fraction','role_score','retention_ratio']);
export function observedText(value){
 if(value === null || value === undefined)return 'Нет данных';
 if(Array.isArray(value))return value.join(', ');
 if(value && typeof value==='object')return Object.entries(value).map(([k,v])=>`${metricName(k)}: ${v===null?'Нет данных':typeof v==='boolean'?(v?'да':'нет'):percentMetrics.has(k)?`${new Intl.NumberFormat('ru-RU',{maximumFractionDigits:1}).format(v*100)}%`:typeof v==='number'?new Intl.NumberFormat('ru-RU',{maximumFractionDigits:4}).format(v):observedText(v)}`).join(' · ');
 return typeof value==='number'?new Intl.NumberFormat('ru-RU').format(value):String(value);
}
export const rules = {
 COLLECTOR:'Не менее 5 разных отправителей.',FAN_IN:'Не менее 5 разных отправителей.',DISTRIBUTOR:'Не менее 5 разных получателей.',FAN_OUT:'Не менее 5 разных получателей.',
 CONSOLIDATOR:'Не менее 2 входящих ветвей, у каждой — не менее 2 собственных источников.',BRIDGE:'Соседи из 2 или более групп и показатель посредничества не ниже 0,02.',
 RAPID_PASS_THROUGH:'Не менее 60% входящего объёма сопоставлено с переводами дальше за 60 минут; доля оборота — не менее 70%.',
 POTENTIAL_MULE_PATTERN:'Одновременно: не менее 5 источников, быстрые переводы от 60%, оборот от 80% и не менее 3 получателей. Независимость владельцев источников не установлена.'
};
