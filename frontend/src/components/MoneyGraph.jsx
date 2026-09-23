import {useEffect,useRef} from 'react';
import cytoscape from 'cytoscape';
import {Plus,Minus,Maximize,RotateCcw} from 'lucide-react';
import {roles,roleColors} from '../services/labels';

const communityPalette=['#518d72','#658ab9','#b68b4b','#9b74aa','#b56972','#729d43','#559eaa','#ac8269'];
function communityColor(value) {
  let hash=0;
  for(const character of String(value??0))hash=(hash*31+character.charCodeAt(0))>>>0;
  return communityPalette[hash%communityPalette.length];
}

// A deterministic O(n log n) layout keeps all accounts on the canvas without a force simulation.
function groupedPositions(nodes) {
  const groups=new Map();
  for(const node of nodes){const key=String(node.data.community_id??node.data.cluster_id??0);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(node);}
  const ordered=[...groups.entries()].sort((a,b)=>b[1].length-a[1].length||a[0].localeCompare(b[0]));
  const targetWidth=Math.max(900,Math.sqrt(nodes.length)*65);
  let x=0,y=0,rowHeight=0;
  const result=[];
  for(const [,group] of ordered){
    group.sort((a,b)=>String(a.data.id).localeCompare(String(b.data.id)));
    const radius=Math.max(36,Math.sqrt(group.length)*21),size=radius*2+100;
    if(x>0&&x+size>targetWidth){x=0;y+=rowHeight;rowHeight=0;}
    group.forEach((node,index)=>{const distance=index===0?0:21*Math.sqrt(index),angle=index*2.39996323;result.push({...node,position:{x:x+size/2+Math.cos(angle)*distance,y:y+size/2+Math.sin(angle)*distance}});});
    x+=size;rowHeight=Math.max(rowHeight,size);
  }
  return result;
}

export default function MoneyGraph({graph,selected,onSelect,priority,pattern,role,minAmount,maxAmount,followIds,resetKey,focusKey,colorMode}) {
  const container=useRef(),cy=useRef(),selectRef=useRef(onSelect),previousSelection=useRef(''),previousFocus=useRef(focusKey);
  selectRef.current=onSelect;
  const large=graph.nodes.length>300;
  useEffect(()=>{
    const normalized=graph.nodes.map(node=>({...node,data:{...node.data,id:String(node.data.id),label:String(node.data.label??node.data.id)}}));
    const nodes=large?groupedPositions(normalized):normalized.map((node,index)=>({...node,position:{x:Math.cos(index*2.39996)*(120+Math.sqrt(index)*35),y:Math.sin(index*2.39996)*(120+Math.sqrt(index)*35)}}));
    const edges=graph.edges.map(edge=>({...edge,data:{...edge.data,id:String(edge.data.id),source:String(edge.data.source),target:String(edge.data.target)}}));
    const instance=cytoscape({container:container.current,elements:[...nodes,...edges],minZoom:.02,maxZoom:4,wheelSensitivity:.18,hideEdgesOnViewport:large,textureOnViewport:large,
      layout:large?{name:'preset',fit:true,padding:55}:{name:'cose',randomize:false,animate:false,nodeRepulsion:()=>16000,idealEdgeLength:()=>100,gravity:.2,numIter:700,padding:55},
      style:[
        {selector:'node',style:{'background-color':'#91ab82','border-color':'#ffffff','border-width':1,'label':'data(label)','font-family':'Segoe UI, Arial, sans-serif','font-size':large?10:12,'min-zoomed-font-size':large?10:7,'font-weight':600,'color':'#34543a','text-valign':'bottom','text-margin-y':7,'text-outline-color':'#ffffff','text-outline-width':2,'width':large?'mapData(priority_score,0,100,9,30)':'mapData(priority_score,0,100,18,48)','height':large?'mapData(priority_score,0,100,9,30)':'mapData(priority_score,0,100,18,48)'}},
        {selector:'edge',style:{'width':large?.65:1,'line-color':'#b7c6b1','target-arrow-color':'#8ca780','target-arrow-shape':'triangle','arrow-scale':large?.4:.6,'curve-style':'bezier','opacity':large?.28:.55}},
        {selector:'.focused',style:{'border-width':4,'border-color':'#234b20','overlay-color':'#8acb55','overlay-opacity':.12,'overlay-padding':8,'z-index':20,'min-zoomed-font-size':0,'font-size':13}},
        {selector:'.flow',style:{'line-color':'#4c9c2b','target-arrow-color':'#4c9c2b','width':2,'opacity':.9}},
        {selector:'.dim',style:{'opacity':.055}},
        {selector:'.filtered',style:{display:'none'}}
      ]});
    cy.current=instance;
    previousSelection.current=selected;
    previousFocus.current=focusKey;
    instance.on('tap','node',event=>selectRef.current(event.target.id()));
    const observer=new ResizeObserver(()=>instance.resize());
    observer.observe(container.current);
    return()=>{observer.disconnect();instance.destroy();cy.current=null;};
  },[graph]);
  useEffect(()=>{
    const instance=cy.current;if(!instance)return;
    instance.batch(()=>instance.nodes().forEach(node=>{
      const color=colorMode==='communities'?communityColor(node.data('community_id')??node.data('cluster_id')):colorMode==='priority'?({HIGH:'#d66477',MEDIUM:'#dba64a',LOW:'#8abc65'}[node.data('priority_level')]||'#9ca895'):roleColors[node.data('role')]||roleColors.peripheral;
      node.style('background-color',color);
    }));
  },[graph,colorMode]);
  useEffect(()=>{
    const instance=cy.current;if(!instance)return;
    instance.batch(()=>{
      instance.elements().removeClass('filtered dim flow focused');
      instance.nodes().forEach(node=>{if((priority!=='ALL'&&node.data('priority_level')!==priority)||(pattern!=='ALL'&&!(node.data('patterns')||[]).includes(pattern))||(role!=='ALL'&&node.data('role')!==role))node.addClass('filtered');});
      instance.edges().forEach(edge=>{if(edge.source().hasClass('filtered')||edge.target().hasClass('filtered')||(minAmount!==''&&edge.data('amount')<Number(minAmount))||(maxAmount!==''&&edge.data('amount')>Number(maxAmount)))edge.addClass('filtered');});
      if(followIds){const ids=new Set(followIds);instance.nodes().forEach(node=>{if(!ids.has(node.id()))node.addClass('dim');});instance.edges().forEach(edge=>edge.addClass(ids.has(edge.source().id())&&ids.has(edge.target().id())?'flow':'dim'));}
      if(selected)instance.getElementById(selected).addClass('focused');
    });
  },[graph,priority,pattern,role,minAmount,maxAmount,followIds,selected]);
  useEffect(()=>{
    const instance=cy.current;
    if(instance&&selected&&(previousSelection.current!==selected||previousFocus.current!==focusKey)){const node=instance.getElementById(selected);if(node.length)instance.animate({center:{eles:node},zoom:Math.max(instance.zoom(),large?.7:.9),duration:200});}
    previousSelection.current=selected;
    previousFocus.current=focusKey;
  },[selected,graph,focusKey]);
  useEffect(()=>{cy.current?.fit(undefined,55);},[resetKey]);
  const resetLayout=()=>{
    const instance=cy.current;if(!instance)return;
    if(large){const positions=new Map(groupedPositions(graph.nodes).map(node=>[String(node.data.id),node.position]));instance.nodes().positions(node=>positions.get(node.id()));instance.fit(undefined,55);}
    else instance.layout({name:'cose',randomize:false,animate:false,padding:55}).run();
  };
  return <div className={`graph-canvas-wrap ${large?'large-graph':''}`}>
    <div className="graph-canvas" ref={container} role="img" aria-label={`Граф: ${graph.nodes.length} счетов, ${graph.edges.length} переводов. Для выбора по клавиатуре используйте поиск или очередь проверки.`}/>
    <div className="graph-caption"><span className="live-dot"/>{graph.nodes.length} СЧЕТОВ · {graph.edges.length} ПЕРЕВОДОВ<small>{large?'Расположение по группам':'Направленная сеть'}</small></div>
    <div className="graph-controls"><button title="Приблизить" aria-label="Приблизить" onClick={()=>cy.current?.zoom(Math.min(4,cy.current.zoom()*1.3))}><Plus size={18}/></button><button title="Отдалить" aria-label="Отдалить" onClick={()=>cy.current?.zoom(Math.max(.02,cy.current.zoom()/1.3))}><Minus size={18}/></button><button title="Вместить граф" aria-label="Вместить граф" onClick={()=>cy.current?.fit(undefined,55)}><Maximize size={18}/></button><button title="Сбросить расположение" aria-label="Сбросить расположение" onClick={resetLayout}><RotateCcw size={18}/></button></div>
    <div className="graph-legend">{colorMode==='roles'?Object.entries(roles).map(([key,label])=><span key={key}><i className="dot" style={{background:roleColors[key]}}/>{label}</span>):colorMode==='priority'?<><span><i className="dot low-bg"/>Низкий</span><span><i className="dot medium-bg"/>Средний</span><span><i className="dot high-bg"/>Высокий приоритет</span></>:<span>Цвет обозначает группу связанных счетов</span>}<span className="legend-hint">Размер — приоритет · Стрелка — перевод</span></div>
  </div>;
}
