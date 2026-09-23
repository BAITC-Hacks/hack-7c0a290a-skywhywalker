let dataset = 'demo';
export const setDataset = id => { dataset=id; };
export async function api(path, body, options={}) {
  const isFile=body instanceof FormData;
  const res=await fetch(`/api${path}`,{method:body===undefined?'GET':'POST',headers:{'X-Dataset-ID':dataset,...(!isFile&&body!==undefined?{'Content-Type':'application/json'}:{})},body:body===undefined?undefined:isFile?body:JSON.stringify(body),...options});
  let data; try {data=await res.json();} catch {throw new Error('Сервер вернул некорректный ответ. Проверьте, запущен ли сервер приложения.');}
  if(!res.ok) throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||'Ошибка запроса'));
  return data;
}
export const fmt = v => new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(v??0);
export const short = v => new Intl.NumberFormat('ru-RU',{notation:'compact',maximumFractionDigits:1}).format(v??0);
export {patternName as patternLabel} from './labels';
