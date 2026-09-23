import {useRef} from 'react';
import {Upload,Play,LoaderCircle,Download} from 'lucide-react';

export default function UploadPanel({busy,onUpload,onAnalyze,onExport,hasGraph}) {
  const input = useRef();
  return <div className="upload-actions">
    <input ref={input} type="file" accept=".csv,.parquet,.zip,text/csv,application/zip" hidden onChange={e=>{if(e.target.files[0])onUpload(e.target.files[0]);e.target.value='';}}/>
    <button disabled={busy} onClick={()=>input.current.click()} title="CSV, файл операций Parquet или ZIP с тремя Parquet"><Upload size={17}/>Загрузить данные</button>
    <button className="primary" disabled={busy} onClick={onAnalyze}>{busy?<LoaderCircle size={17} className="spin"/>:<Play size={17}/>}Построить граф</button>
    <button disabled={busy||!hasGraph} onClick={onExport} title="Архив: роли всех счетов, группы, топ приоритетов"><Download size={17}/>Скачать 3 CSV</button>
  </div>;
}
