import {useRef} from 'react';
import {Upload,Play,LoaderCircle} from 'lucide-react';
export default function UploadPanel({busy,onUpload,onAnalyze}){
 const input=useRef();
 return <div className="upload-actions"><input ref={input} type="file" accept=".csv,text/csv" hidden onChange={e=>{if(e.target.files[0])onUpload(e.target.files[0]);e.target.value='';}}/><button disabled={busy} onClick={()=>input.current.click()}><Upload size={17}/>Загрузить CSV</button><button className="primary" disabled={busy} onClick={onAnalyze}>{busy?<LoaderCircle size={17} className="spin"/>:<Play size={17}/>}Построить граф</button></div>
}
