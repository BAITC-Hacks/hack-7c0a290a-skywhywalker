import {useEffect,useRef} from 'react';
import cytoscape from 'cytoscape';
import {Plus,Minus,Maximize,RotateCcw} from 'lucide-react';
export default function MoneyGraph({graph,selected,onSelect,priority,pattern,minAmount,maxAmount,followIds,resetKey}) {
 const container=useRef(), cy=useRef(), selectRef=useRef(onSelect);
 selectRef.current=onSelect;
 useEffect(()=>{
  if(!graph||!container.current)return;
  const nodes=graph.nodes.map((n,i)=>({...n,position:{x:Math.cos(i*2.39996)*(120+Math.sqrt(i)*35),y:Math.sin(i*2.39996)*(120+Math.sqrt(i)*35)}}));
  const instance=cytoscape({container:container.current,elements:[...nodes,...graph.edges],minZoom:.12,maxZoom:4,wheelSensitivity:.18,layout:{name:'cose',randomize:false,animate:false,nodeRepulsion:()=>16000,idealEdgeLength:()=>100,gravity:.2,numIter:700,padding:55},style:[
   {selector:'node',style:{'background-color':'#cce9bd','border-color':'#78ad53','border-width':1.5,'label':'data(label)','font-family':'Inter, Segoe UI, sans-serif','font-size':12,'font-weight':600,'color':'#34543a','text-valign':'bottom','text-margin-y':8,'text-outline-color':'#ffffff','text-outline-width':2,'width':'mapData(priority_score,0,100,18,48)','height':'mapData(priority_score,0,100,18,48)'}},
   {selector:'node[priority_level="MEDIUM"]',style:{'background-color':'#ffe4b1','border-color':'#d89738','color':'#785015'}},
   {selector:'node[priority_level="HIGH"]',style:{'background-color':'#f6cbd2','border-color':'#d95d70','color':'#7c2636'}},
   {selector:'edge',style:{'width':1,'line-color':'#b7c6b1','target-arrow-color':'#8ca780','target-arrow-shape':'triangle','arrow-scale':.6,'curve-style':'bezier','opacity':.55}},
   {selector:'.focused',style:{'border-width':4,'border-color':'#2a661f','overlay-color':'#8acb55','overlay-opacity':.12,'overlay-padding':9,'z-index':20}},
   {selector:'.flow',style:{'line-color':'#4c9c2b','target-arrow-color':'#4c9c2b','width':2,'opacity':.9}},
   {selector:'.dim',style:{'opacity':.07}}, {selector:'.filtered',style:{display:'none'}}
  ]});
  cy.current=instance;
  instance.on('tap','node',e=>selectRef.current(e.target.id()));
  const observer=new ResizeObserver(()=>{instance.resize();instance.fit(undefined,45);});observer.observe(container.current);
  return()=>{observer.disconnect();instance.destroy();cy.current=null;};
 },[graph]);
 useEffect(()=>{
  const c=cy.current;if(!c)return;
  c.batch(()=>{
   c.elements().removeClass('filtered dim flow focused');
   c.nodes().forEach(n=>{if((priority!=='ALL'&&n.data('priority_level')!==priority)||(pattern!=='ALL'&&!n.data('patterns').includes(pattern)))n.addClass('filtered');});
   c.edges().forEach(e=>{if(e.source().hasClass('filtered')||e.target().hasClass('filtered')||(minAmount!==''&&e.data('amount')<Number(minAmount))||(maxAmount!==''&&e.data('amount')>Number(maxAmount)))e.addClass('filtered');});
   if(followIds){const ids=new Set(followIds);c.nodes().forEach(n=>{if(!ids.has(n.id()))n.addClass('dim');});c.edges().forEach(e=>e.addClass(ids.has(e.source().id())&&ids.has(e.target().id())?'flow':'dim'));}
   if(selected)c.getElementById(selected).addClass('focused');
  });
 },[graph,priority,pattern,minAmount,maxAmount,followIds,selected]);
 useEffect(()=>{const c=cy.current;if(c&&selected){const n=c.getElementById(selected);if(n.length)c.animate({center:{eles:n},zoom:Math.max(c.zoom(),.9),duration:250});}},[selected]);
 useEffect(()=>{cy.current?.fit(undefined,55);},[resetKey]);
 return <div className="graph-canvas-wrap"><div className="graph-canvas" ref={container} role="img" aria-label="Интерактивный граф транзакций. Выберите счёт из доступного списка слева."/><div className="graph-caption"><span className="live-dot"/> НАПРАВЛЕНИЕ ДВИЖЕНИЯ ДЕНЕГ <small>{graph?.stats.links??0} связей между счетами</small></div><div className="graph-controls"><button title="Приблизить" aria-label="Приблизить" onClick={()=>cy.current?.zoom(cy.current.zoom()*1.2)}><Plus size={18}/></button><button title="Отдалить" aria-label="Отдалить" onClick={()=>cy.current?.zoom(cy.current.zoom()/1.2)}><Minus size={18}/></button><button title="Вместить граф" aria-label="Вместить граф" onClick={()=>cy.current?.fit(undefined,55)}><Maximize size={17}/></button><button title="Сбросить расположение" aria-label="Сбросить расположение" onClick={()=>cy.current?.layout({name:'cose',randomize:false,animate:false,padding:55}).run()}><RotateCcw size={17}/></button></div><div className="graph-legend"><span><i className="dot low-bg"/>Низкий</span><span><i className="dot medium-bg"/>Средний</span><span><i className="dot high-bg"/>Высокий приоритет</span><span className="legend-hint">Размер = приоритет · Стрелка = направление</span></div></div>
}

