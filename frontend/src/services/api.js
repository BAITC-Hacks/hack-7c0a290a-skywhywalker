let dataset = 'official';
export const setDataset = id => { dataset=id; };
export async function api(path, body, options={}) {
  const isFile=body instanceof FormData;
  const res=await fetch(`/api${path}`,{method:body===undefined?'GET':'POST',headers:{'X-Dataset-ID':dataset,...(!isFile&&body!==undefined?{'Content-Type':'application/json'}:{})},body:body===undefined?undefined:isFile?body:JSON.stringify(body),...options});
  let data; try {data=await res.json();} catch {throw new Error('Сервер вернул некорректный ответ. Проверьте, запущен ли сервер приложения.');}
  if(!res.ok) throw new Error(typeof data.detail==='string'?data.detail:'Не удалось обработать запрос. Проверьте выбранные данные и попробуйте снова.');
  return data;
}
export const fmt = v => new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(v??0);
export const short = v => new Intl.NumberFormat('ru-RU',{notation:'compact',maximumFractionDigits:1}).format(v??0);
export async function downloadExports() {
  const response = await fetch('/api/export', {headers:{'X-Dataset-ID':dataset}});
  if (!response.ok) {
    let detail;
    try { detail = (await response.json()).detail; } catch { /* Friendly fallback below. */ }
    throw new Error(typeof detail === 'string' ? detail : 'Не удалось подготовить выгрузки.');
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = 'moneygraph-results.zip';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
export const amountUnit = currency => currency === 'KZT' ? 'KZT' : 'ед. файла';
export const dateLabel = (value, precision='timestamp') => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return precision === 'day' ? date.toLocaleDateString('ru-RU',{timeZone:'UTC'}) : date.toLocaleString('ru-RU',{timeZone:'UTC'});
};
export {patternName as patternLabel} from './labels';
