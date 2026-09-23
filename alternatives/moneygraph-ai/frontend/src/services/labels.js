export const levels = {ALL:'Все приоритеты',HIGH:'Высокий',MEDIUM:'Средний',LOW:'Низкий'};
export const components = {graph_score:'Связи в сети',anomaly_score:'Необычность',pattern_score:'Схемы переводов',flow_score:'Движение денег'};
export const patterns = {
  COLLECTOR:['Сбор средств','На счёт поступают деньги как минимум от пяти разных отправителей.'],
  FAN_IN:['Много отправителей','Несколько входящих потоков сходятся в одном счёте.'],
  DISTRIBUTOR:['Распределение средств','Счёт отправляет деньги как минимум пяти разным получателям.'],
  FAN_OUT:['Много получателей','Счёт переводит деньги пяти или более разным получателям.'],
  CONSOLIDATOR:['Объединение потоков','На счёте сходятся как минимум две ветви, каждая — с несколькими источниками.'],
  BRIDGE:['Связь между группами','Счёт соединяет разные группы и часто находится на путях между другими счетами.'],
  RAPID_PASS_THROUGH:['Быстрый перевод дальше','Значительная часть поступлений сопоставлена с исходящими переводами в пределах часа.'],
  POTENTIAL_MULE_PATTERN:['Возможный посреднический счёт','Совпали четыре признака: много отправителей, быстрый перевод дальше, высокий оборот и несколько получателей. Это повод изучить контекст, а не вывод о владельце.']
};
export const patternName = key => patterns[key]?.[0] || key;
export const patternHint = key => patterns[key]?.[1] || '';
export const metrics = {
 incoming_transaction_count:'Входящих переводов',outgoing_transaction_count:'Исходящих переводов',transaction_count:'Всего переводов',
 incoming_counterparties:'Разных отправителей',outgoing_counterparties:'Разных получателей',total_incoming_amount:'Сумма поступлений',total_outgoing_amount:'Сумма отправлений',
 total_volume:'Общий объём переводов',in_out_ratio:'Поступления / отправления',turnover_ratio:'Доля оборота',degree_centrality:'Доля связей в сети',in_degree:'Входящих связей',out_degree:'Исходящих связей',
 betweenness:'Роль посредника в сети',pagerank:'Значимость счёта в сети',community_id:'Номер группы',average_incoming_amount:'Средний входящий перевод',average_outgoing_amount:'Средний исходящий перевод',median_amount:'Медианная сумма перевода',communities_connected:'Связанных групп',matched_amount:'Сопоставленная сумма',rapid_amount:'Сумма быстрых переводов',rapid_share:'Доля быстрых переводов',average_holding_minutes:'Среднее время до перевода, мин.',
 communities:'Связанных групп',turnover:'Доля оборота',multiple_sources:'Несколько отправителей',rapid_forwarding:'Быстрый перевод дальше',high_turnover:'Высокий оборот',fan_in_fan_out:'Несколько отправителей и получателей'
};
export const metricName = key => metrics[key] || components[key] || key;
export const percentMetrics = new Set(['rapid_share','turnover_ratio','turnover']);
export function observedText(value){
 if(Array.isArray(value))return value.join(', ');
 if(value && typeof value==='object')return Object.entries(value).map(([k,v])=>`${metricName(k)}: ${typeof v==='boolean'?(v?'да':'нет'):percentMetrics.has(k)?`${(v*100).toFixed(1)}%`:typeof v==='number'?new Intl.NumberFormat('ru-RU',{maximumFractionDigits:4}).format(v):observedText(v)}`).join(' · ');
 return typeof value==='number'?new Intl.NumberFormat('ru-RU').format(value):String(value);
}
export const rules = {
 COLLECTOR:'Не менее 5 разных отправителей.',FAN_IN:'Не менее 5 разных отправителей.',DISTRIBUTOR:'Не менее 5 разных получателей.',FAN_OUT:'Не менее 5 разных получателей.',
 CONSOLIDATOR:'Не менее 2 входящих ветвей, у каждой — не менее 2 собственных источников.',BRIDGE:'Соседи из 2 или более групп и показатель посредничества не ниже 0,02.',
 RAPID_PASS_THROUGH:'Не менее 60% входящего объёма сопоставлено с переводами дальше за 60 минут; доля оборота — не менее 70%.',
 POTENTIAL_MULE_PATTERN:'Одновременно: не менее 5 источников, быстрые переводы от 60%, оборот от 80% и не менее 3 получателей. Независимость владельцев источников не установлена.'
};
