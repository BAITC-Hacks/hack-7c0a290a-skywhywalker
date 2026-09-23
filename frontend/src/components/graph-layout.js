// Pure transformations. Only observed, directed transactions are aggregated.
export const shortId=value=>String(value).length>11?`…${String(value).slice(-9)}`:String(value);
export function aggregateTransactions(edges,{minAmount='',maxAmount=''}={}) {
  const pairs=new Map();
  for(const edge of edges){const tx=edge.data,amount=Number(tx.amount);if(!Number.isFinite(amount)||(minAmount!==''&&amount<Number(minAmount))||(maxAmount!==''&&amount>Number(maxAmount)))continue;const source=String(tx.source),target=String(tx.target),key=JSON.stringify([source,target]);if(!pairs.has(key))pairs.set(key,{source,target,amount:0,n_tx:0,transaction_ids:[]});const pair=pairs.get(key);pair.amount+=amount;pair.n_tx++;pair.transaction_ids.push(String(tx.transaction_id??tx.id));}
  return [...pairs.values()].sort((a,b)=>b.amount-a.amount||a.source.localeCompare(b.source)||a.target.localeCompare(b.target));
}
function accepts(data,{priority='ALL',pattern='ALL',role='ALL'}){return(priority==='ALL'||data.priority_level===priority)&&(role==='ALL'||data.role===role)&&(pattern==='ALL'||(data.patterns||[]).includes(pattern));}
export function buildGraphView(graph,selected,options={}) {
  const {mode='focus',followIds=null,neighborLimit=4,hopLimit=80}=options,selectedId=String(selected??'');
  const allNodes=new Map(graph.nodes.map(node=>[String(node.data.id),{...node,data:{...node.data,id:String(node.data.id)}}]));
  const eligible=new Set([...allNodes].filter(([,node])=>accepts(node.data,options)).map(([id])=>id));
  const selectedFiltered=allNodes.has(selectedId)&&!eligible.has(selectedId);
  if(allNodes.has(selectedId))eligible.add(selectedId); // Explicitly disclosed context node.
  const pairs=aggregateTransactions(graph.edges,options).filter(edge=>eligible.has(edge.source)&&eligible.has(edge.target));
  const incoming=pairs.filter(edge=>edge.target===selectedId&&edge.source!==selectedId),outgoing=pairs.filter(edge=>edge.source===selectedId&&edge.target!==selectedId);
  let ids,available,kind;
  if(mode==='all'){ids=new Set(eligible);available=ids.size;kind='all';}
  else if(followIds){
    const allowed=new Set(followIds.map(String).filter(id=>eligible.has(id)));if(allNodes.has(selectedId))allowed.add(selectedId);
    const volume=new Map();for(const edge of pairs)if(allowed.has(edge.source)&&allowed.has(edge.target)){volume.set(edge.source,(volume.get(edge.source)||0)+edge.amount);volume.set(edge.target,(volume.get(edge.target)||0)+edge.amount);}
    const ranked=[...allowed].filter(id=>id!==selectedId).sort((a,b)=>(volume.get(b)||0)-(volume.get(a)||0)||(allNodes.get(b).data.priority_score||0)-(allNodes.get(a).data.priority_score||0)||a.localeCompare(b));
    const cap=Math.max(1,Math.min(80,hopLimit));ids=new Set(allNodes.has(selectedId)?[selectedId,...ranked.slice(0,cap-1)]:ranked.slice(0,cap));available=allowed.size;kind='hops';
  }else{
    const limit=Math.max(1,Math.min(12,neighborLimit));ids=new Set(allNodes.has(selectedId)?[selectedId]:[]);incoming.slice(0,limit).forEach(edge=>ids.add(edge.source));outgoing.slice(0,limit).forEach(edge=>ids.add(edge.target));
    available=new Set([...incoming.map(edge=>edge.source),...outgoing.map(edge=>edge.target),...(allNodes.has(selectedId)?[selectedId]:[])]).size;kind='focus';
  }
  let prefix='__flow_pair__';while([...allNodes.keys()].some(id=>id.startsWith(prefix)))prefix+='_';
  const visiblePairs=pairs.filter(edge=>ids.has(edge.source)&&ids.has(edge.target)&&(kind!=='focus'||edge.source===selectedId||edge.target===selectedId));
  const incomingIds=new Set(incoming.map(edge=>edge.source)),outgoingIds=new Set(outgoing.map(edge=>edge.target));
  const nodes=[...ids].map(id=>({...allNodes.get(id),data:{...allNodes.get(id).data,label:shortId(id),mutual:incomingIds.has(id)&&outgoingIds.has(id)}}));
  return {nodes,edges:visiblePairs.map((pair,index)=>({data:{...pair,id:`${prefix}${index}`}})),kind,selectedFiltered,availableNodes:available,totalNodes:allNodes.size,omittedNodes:Math.max(0,available-ids.size),totalIncoming:incoming.length,totalOutgoing:outgoing.length,shownIncoming:visiblePairs.filter(edge=>edge.target===selectedId&&edge.source!==selectedId).length,shownOutgoing:visiblePairs.filter(edge=>edge.source===selectedId&&edge.target!==selectedId).length,transactionCount:visiblePairs.reduce((sum,edge)=>sum+edge.n_tx,0),noObservedEdges:!graph.edges.some(edge=>String(edge.data.source)===selectedId||String(edge.data.target)===selectedId)};
}
export function focusPositions(nodes,edges,selected) {
  const selectedId=String(selected),incoming=new Map(),outgoing=new Map();for(const {data:edge} of edges){if(edge.target===selectedId&&edge.source!==selectedId)incoming.set(edge.source,edge.amount);if(edge.source===selectedId&&edge.target!==selectedId)outgoing.set(edge.target,edge.amount);}
  const left=[],right=[];for(const node of nodes){if(node.data.id===selectedId)continue;((incoming.get(node.data.id)||0)>=(outgoing.get(node.data.id)||0)?left:right).push(node);}
  const rank=(a,b)=>Math.max(incoming.get(b.data.id)||0,outgoing.get(b.data.id)||0)-Math.max(incoming.get(a.data.id)||0,outgoing.get(a.data.id)||0)||a.data.id.localeCompare(b.data.id);left.sort(rank);right.sort(rank);
  const result=nodes.filter(node=>node.data.id===selectedId).map(node=>({...node,position:{x:320,y:0}}));for(const [lane,x] of [[left,0],[right,640]])lane.forEach((node,index)=>result.push({...node,position:{x,y:(index-(lane.length-1)/2)*98}}));return result;
}
export function groupedPositions(nodes) {
  const groups=new Map();for(const node of nodes){const key=String(node.data.community_id??node.data.cluster_id??0);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(node);}
  const ordered=[...groups.entries()].sort((a,b)=>b[1].length-a[1].length||a[0].localeCompare(b[0]));const targetWidth=Math.max(900,Math.sqrt(nodes.length)*65);let x=0,y=0,rowHeight=0;const result=[];
  for(const [,group] of ordered){group.sort((a,b)=>String(a.data.id).localeCompare(String(b.data.id)));const radius=Math.max(36,Math.sqrt(group.length)*21),size=radius*2+100;if(x>0&&x+size>targetWidth){x=0;y+=rowHeight;rowHeight=0;}group.forEach((node,index)=>{const distance=index===0?0:21*Math.sqrt(index),angle=index*2.39996323;result.push({...node,position:{x:x+size/2+Math.cos(angle)*distance,y:y+size/2+Math.sin(angle)*distance}});});x+=size;rowHeight=Math.max(rowHeight,size);}return result;
}
