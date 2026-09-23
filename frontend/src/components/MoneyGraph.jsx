import {useEffect,useMemo,useRef,useState} from 'react';
import cytoscape from 'cytoscape';
import {Plus,Minus,Maximize,RotateCcw,Focus,Network,ArrowRight,X} from 'lucide-react';
import {roles,roleColors,roleName} from '../services/labels';
import {buildGraphView,focusPositions,groupedPositions,shortId} from './graph-layout';
import './graph-focus.css';

const palette=['#518d72','#658ab9','#b68b4b','#9b74aa','#b56972','#729d43','#559eaa','#ac8269'];
function communityColor(value){let hash=0;for(const character of String(value??0))hash=(hash*31+character.charCodeAt(0))>>>0;return palette[hash%palette.length];}
const amountText=(value,currency)=>`${new Intl.NumberFormat('ru-RU',{notation:'compact',maximumFractionDigits:1}).format(value)} ${currency==='KZT'?'₸':'ед.'}`;
const exactAmount=(value,currency)=>`${new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(value)} ${currency==='KZT'?'₸':'ед. файла'}`;
function fitGraph(instance,kind){
  if(instance.nodes().length===1){instance.zoom(1);instance.center();return;}
  if(kind==='focus'){const box=instance.elements().boundingBox();instance.fit({x1:-90,x2:730,y1:Math.min(box.y1,-55),y2:Math.max(box.y2,55)},22);}
  else instance.fit(undefined,45);
}

export default function MoneyGraph({graph,selected,onSelect,priority='ALL',pattern='ALL',role='ALL',minAmount='',maxAmount='',followIds,resetKey,focusKey,colorMode='roles',viewMode='focus',onEvidence}) {
  const container=useRef(),cy=useRef(),selectRef=useRef(onSelect);
  const [mode,setMode]=useState(viewMode),[neighborLimit,setNeighborLimit]=useState(4),[tooltip,setTooltip]=useState(null),[edgeDetail,setEdgeDetail]=useState(null);
  selectRef.current=onSelect;
  const view=useMemo(()=>buildGraphView(graph,selected,{mode,followIds,neighborLimit,priority,pattern,role,minAmount,maxAmount}),[graph,selected,mode,followIds,neighborLimit,priority,pattern,role,minAmount,maxAmount]);
  const compact=view.kind!=='all',large=view.nodes.length>300,currency=graph.stats?.currency;
  useEffect(()=>{setMode('focus');setEdgeDetail(null);setTooltip(null);},[selected,focusKey]);
  useEffect(()=>{setMode(viewMode);},[viewMode]);
  useEffect(()=>{if(followIds)setMode('focus');},[followIds]);
  useEffect(()=>{
    setEdgeDetail(null);setTooltip(null);
    const normalized=view.nodes.map(node=>({...node,data:{...node.data,displayLabel:`${node.data.mutual?'↔ ':''}${shortId(node.data.id)}${compact?`\n${roleName(node.data.role)}`:''}`}}));
    const nodes=view.kind==='focus'?focusPositions(normalized,view.edges,selected):large?groupedPositions(normalized):normalized.map((node,index)=>({...node,position:{x:Math.cos(index*2.39996323)*(90+Math.sqrt(index)*45),y:Math.sin(index*2.39996323)*(90+Math.sqrt(index)*45)}}));
    const edges=view.edges.map(edge=>({...edge,data:{...edge.data,flowLabel:`${amountText(edge.data.amount,currency)}\n${edge.data.n_tx} пер.`}}));
    const instance=cytoscape({container:container.current,elements:[...nodes,...edges],minZoom:.025,maxZoom:3,wheelSensitivity:.18,hideEdgesOnViewport:large,textureOnViewport:large,
      layout:view.kind==='focus'||large?{name:'preset',fit:true,padding:42}:{name:'cose',randomize:false,animate:false,nodeRepulsion:()=>18000,idealEdgeLength:()=>135,gravity:.18,numIter:400,padding:45},
      style:[
        {selector:'node',style:{'shape':compact?'round-rectangle':'ellipse','background-color':'#FFFFFF','border-color':'#B6D1BC','border-width':compact?1.5:1,'label':'data(displayLabel)','font-family':'Segoe UI, Arial, sans-serif','font-size':compact?17:10,'min-zoomed-font-size':compact?0:9,'font-weight':600,'color':'#224C36','text-valign':compact?'center':'bottom','text-margin-y':compact?0:6,'text-wrap':'wrap','text-max-width':compact?162:110,'line-height':1.3,'text-outline-color':'#FFFFFF','text-outline-width':compact?0:2,'width':compact?174:'mapData(priority_score,0,100,9,30)','height':compact?80:'mapData(priority_score,0,100,9,30)','overlay-opacity':0}},
        {selector:'edge',style:{'width':compact?1.8:.7,'line-color':compact?'#6C9D7B':'#ADC2B2','target-arrow-color':compact?'#438257':'#89A991','target-arrow-shape':'triangle','arrow-scale':compact?1:.45,'curve-style':'bezier','opacity':compact?.9:.3,'label':compact?'data(flowLabel)':'','font-size':compact?14:11,'color':'#3C5E44','text-wrap':'wrap','text-rotation':'none','text-background-color':'#FAFDFB','text-background-opacity':.98,'text-background-padding':4,'text-background-shape':'roundrectangle','text-border-color':'#E3EDE6','text-border-width':.5,'text-border-opacity':1,'min-zoomed-font-size':compact?0:11,'loop-direction':'-90deg','loop-sweep':'60deg'}},
        {selector:'.focused',style:{'background-color':'#164B32','border-color':'#164B32','border-width':2,'color':'#FFFFFF','text-outline-width':0,'width':compact?190:36,'height':compact?88:36,'font-size':compact?18:13,'min-zoomed-font-size':0,'z-index':20}},
        {selector:'.selected-filtered',style:{'border-style':'dashed','border-color':'#C79842','border-width':3}},
        {selector:'edge:selected',style:{'line-color':'#246E3E','target-arrow-color':'#246E3E','width':3,'opacity':1}},
      ]});
    cy.current=instance;instance.getElementById(String(selected)).addClass('focused');if(view.selectedFiltered)instance.getElementById(String(selected)).addClass('selected-filtered');
    instance.on('tap','node',event=>selectRef.current(event.target.id()));instance.on('tap','edge',event=>{setEdgeDetail(event.target.data());setTooltip(null);});instance.on('tap',event=>{if(event.target===instance)setEdgeDetail(null);});
    instance.on('mouseover','node',event=>{const data=event.target.data(),position=event.target.renderedPosition();setTooltip({text:`GID ${data.id} · ${roleName(data.role)}${data.is_seed?' · исходный счёт':''}`,x:position.x,y:position.y});});instance.on('mouseout','node',()=>setTooltip(null));instance.on('pan zoom',()=>setTooltip(null));
    const fit=()=>{instance.resize();fitGraph(instance,view.kind);};const observer=new ResizeObserver(fit);observer.observe(container.current);fit();
    return()=>{observer.disconnect();instance.destroy();cy.current=null;};
  },[view,selected,compact,large,currency]);
  useEffect(()=>{const instance=cy.current;if(!instance)return;instance.batch(()=>instance.nodes().forEach(node=>{if(node.id()===String(selected))return;const color=colorMode==='communities'?communityColor(node.data('community_id')??node.data('cluster_id')):colorMode==='priority'?({HIGH:'#C45164',MEDIUM:'#B88A35',LOW:'#6FA24D'}[node.data('priority_level')]||'#9CA895'):roleColors[node.data('role')]||roleColors.peripheral;if(compact){node.style('border-color',color);node.style('background-color','#F5FAF5');node.style('border-width',3);}else node.style('background-color',color);}));},[view,colorMode,selected,compact]);
  const fit=()=>{const instance=cy.current;if(instance)fitGraph(instance,view.kind);};
  useEffect(()=>{fit();},[resetKey]);
  const relayout=()=>{const instance=cy.current;if(!instance)return;if(view.kind==='focus'||large){const positions=new Map((view.kind==='focus'?focusPositions(view.nodes,view.edges,selected):groupedPositions(view.nodes)).map(node=>[node.data.id,node.position]));instance.nodes().positions(node=>positions.get(node.id()));fit();}else instance.layout({name:'cose',randomize:false,animate:false,padding:45}).run();};
  const summary=`Показано ${view.nodes.length} из ${view.availableNodes} счетов${view.kind==='all'?' после фильтров':''} · ${view.edges.length} связей · ${view.transactionCount} операций`;
  return <div className={`graph-canvas-wrap mm-graph ${compact?'mm-graph-focus':'mm-graph-all'}`}>
    <div className="mm-graph-toolbar"><div className="mm-view-switch" role="group" aria-label="Режим графа"><button className={mode==='focus'?'active':''} aria-pressed={mode==='focus'} onClick={()=>setMode('focus')}><Focus size={14}/>Связи счёта</button><button className={mode==='all'?'active':''} aria-pressed={mode==='all'} onClick={()=>setMode('all')}><Network size={14}/>Вся сеть</button></div>{view.kind==='focus'&&<label className="mm-density">На сторону<select aria-label="Максимум крупнейших контрагентов с каждой стороны" value={neighborLimit} onChange={event=>setNeighborLimit(Number(event.target.value))}>{[4,8,12].map(n=><option key={n}>{n}</option>)}</select></label>}</div>
    <div className="mm-graph-summary" role="status"><b>{view.kind==='focus'?'Прямые наблюдаемые связи':view.kind==='hops'?'Связи в выбранной глубине':'Полная сеть'}</b><span>{summary}</span>{view.omittedNodes>0&&<small>Ещё {view.omittedNodes} счетов не показано: выбраны крупнейшие по объёму. {view.kind==='hops'?'Лимит — 80 счетов.':'Увеличьте число связей или откройте всю сеть.'}</small>}{view.selectedFiltered&&<small>Выбранный счёт не соответствует фильтру и оставлен только для контекста.</small>}</div>
    {view.kind==='focus'&&<div className="mm-flow-lanes" aria-hidden="true"><span>Плательщики <small>{view.shownIncoming}/{view.totalIncoming}</small></span><span>Выбранный счёт</span><span>Получатели <small>{view.shownOutgoing}/{view.totalOutgoing}</small></span></div>}
    <div className="mm-graph-stage"><div className="graph-canvas" ref={container} role="img" aria-label={`${summary}. Выбранный GID ${selected}. Стрелки показывают направление, суммы — объём отфильтрованных операций. Для выбора используйте поиск или список счетов.`}/>{tooltip&&<div className="mm-node-tooltip" role="tooltip" style={{left:Math.min(Math.max(tooltip.x,130),(container.current?.clientWidth||500)-130),top:Math.max(8,tooltip.y-64)}}>{tooltip.text}</div>}{compact&&view.edges.length===0&&<div className="mm-empty-flow">{view.noObservedEdges?'У этого счёта нет переводов в предоставленной выгрузке.':'При выбранных фильтрах связи не найдены.'}</div>}<div className="mm-graph-controls"><button aria-label="Приблизить граф" title="Приблизить" onClick={()=>cy.current?.zoom(Math.min(3,cy.current.zoom()*1.3))}><Plus size={16}/></button><button aria-label="Отдалить граф" title="Отдалить" onClick={()=>cy.current?.zoom(Math.max(.025,cy.current.zoom()/1.3))}><Minus size={16}/></button><button aria-label="Вместить показанные связи" title="Вместить связи" onClick={fit}><Maximize size={16}/></button><button aria-label="Перестроить показанные связи" title="Перестроить" onClick={relayout}><RotateCcw size={16}/></button></div></div>
    {edgeDetail&&<div className="mm-edge-detail"><button className="mm-edge-close" aria-label="Закрыть выбранную связь" onClick={()=>setEdgeDetail(null)}><X size={15}/></button><span>Наблюдаемая связь · {edgeDetail.n_tx} операций</span><div><button onClick={()=>onSelect(edgeDetail.source)} title={edgeDetail.source}>{shortId(edgeDetail.source)}</button><ArrowRight size={15}/><button onClick={()=>onSelect(edgeDetail.target)} title={edgeDetail.target}>{shortId(edgeDetail.target)}</button><b>{exactAmount(edgeDetail.amount,currency)}</b></div>{onEvidence&&<button onClick={()=>onEvidence(selected)}>Проверить исходные операции</button>}</div>}
    <div className="mm-graph-legend">{colorMode==='roles'?Object.entries(roles).map(([key,label])=><span key={key}><i style={{background:roleColors[key]}}/>{label}</span>):colorMode==='priority'?<><span><i style={{background:'#C45164'}}/>Высокий</span><span><i style={{background:'#B88A35'}}/>Средний</span><span><i style={{background:'#6FA24D'}}/>Низкий приоритет</span></>:<span>Цвет — группа связанных счетов</span>}<p>Стрелка — направление · Сумма — после фильтра отдельных операций · ↔ — связь в обе стороны</p></div>
    {compact&&<details className="mm-accessible-nodes"><summary>Выбрать счёт из показанных ({view.nodes.length})</summary><div>{view.nodes.map(({data:node})=><button key={node.id} onClick={()=>onSelect(node.id)} aria-label={`Открыть счёт ${node.id}, ${roleName(node.role)}`} title={`GID ${node.id} · ${roleName(node.role)}`}>{node.id}<small>{roleName(node.role)}</small></button>)}</div></details>}
  </div>;
}
