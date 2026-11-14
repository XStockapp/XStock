"""Gráficos P&L animados del terminal de opciones (calculados en el navegador, Black-Scholes con la IV actual).

1. «Sensibilidad temporal: P&L vs días»: P&L si el subyacente llega al objetivo en el día d (curva de rendimiento) y
   P&L si el precio se queda en el spot (quema de theta). Punto arrastrable = velocidad de llegada.
2. «P&L según precio del subyacente»: curva tras d días y al vencimiento, con spot, strike, breakeven, objetivo y muros.
Ambos gráficos tienen proporción fija (no se estiran a lo ancho) y se dibujan con animación al cargar.
"""
import json

FONT = "'JetBrains Mono','Fira Code',monospace"


def html(spot: float, objetivo: float, contratos: list[dict], dias0: int, rango: tuple[float, float],
         niveles: list[dict] | None = None) -> str:
    """contratos: [{nombre, tipo, strike, iv (fracción), prima, dte, color}] — el primero es el principal."""
    data = json.dumps({"spot": spot, "obj": objetivo, "c": contratos, "d0": dias0, "lo": rango[0], "hi": rango[1],
                       "niv": niveles or []})
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@400;600&display=swap');
*{{box-sizing:border-box}}
body{{margin:0;background:transparent;color:#E6EDF3;font-family:Inter,system-ui,sans-serif;font-size:12px}}
.top{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:0 0 8px}}
.lbl{{color:#8B949E;font-size:11px}}
.num{{font-family:{FONT};font-variant-numeric:tabular-nums}}
.step{{display:flex;align-items:center;border:1px solid #30363D;border-radius:4px}}
.step button{{background:#0D1117;color:#E6EDF3;border:0;width:26px;height:26px;cursor:pointer;font-size:14px}}
.step button:hover{{background:#21262D}}
.step input{{width:76px;height:24px;border:0;border-left:1px solid #30363D;border-right:1px solid #30363D;background:#0D1117;
  color:#E6EDF3;text-align:center;font-family:{FONT};font-size:12px;outline:none}}
.step input:focus{{box-shadow:inset 0 0 0 1px #2962FF}}
.kp{{display:flex;gap:16px;margin-left:auto;flex-wrap:wrap}}
.kp div{{display:flex;flex-direction:column;align-items:flex-end}}
.kp b{{font-family:{FONT};font-variant-numeric:tabular-nums;font-size:14px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:10px}}
.card{{background:#0D1117;border:1px solid #30363D;border-radius:6px;padding:10px 10px 6px;max-width:680px}}
.card h4{{margin:0;font-size:12px;font-weight:600;color:#E6EDF3;display:flex;justify-content:space-between;gap:8px}}
.card h4 span{{color:#8B949E;font-weight:400;font-size:11px}}
.card .sub{{color:#8B949E;font-size:11px;margin:2px 0 4px}}
svg{{width:100%;display:block;overflow:visible}}
svg text{{font-family:{FONT};font-size:11px;fill:#8B949E}}
.leg{{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:#8B949E;margin-top:4px}}
.leg i{{display:inline-block;width:14px;height:2px;margin-right:5px;vertical-align:middle}}
.draw{{stroke-dasharray:var(--l);stroke-dashoffset:var(--l);animation:dr 1.4s ease-out forwards}}
@keyframes dr{{to{{stroke-dashoffset:0}}}}
.fade{{opacity:0;animation:fd 1.2s .5s ease-out forwards}}
@keyframes fd{{to{{opacity:1}}}}
.pulse{{animation:pl 1.6s ease-in-out infinite;transform-box:fill-box;transform-origin:center}}
@keyframes pl{{0%,100%{{opacity:.35;transform:scale(1)}}50%{{opacity:.9;transform:scale(1.6)}}}}
.tag{{font-size:11px}}
</style></head><body>
<div class='top'>
 <span class='lbl'>Días hasta el objetivo</span>
 <div class='step'><button id='dm'>−</button><input id='dl' class='num'><button id='dp'>+</button></div>
 <span class='lbl'>Precio objetivo</span>
 <div class='step'><button id='om'>−</button><input id='obj' class='num'><button id='op'>+</button></div>
 <div class='kp' id='kp'></div>
</div>
<div class='grid'>
 <div class='card'><h4>Sensibilidad temporal: P&amp;L vs días <span id='t1'></span></h4>
  <div class='sub'>Si el precio llega al objetivo en el día elegido · arrastra el punto</div>
  <svg id='g1'></svg>
  <div class='leg'><span><i style='background:#26A69A'></i>Curva de rendimiento</span>
   <span><i style='background:#EF5350'></i>Quema de theta (precio quieto)</span><span id='lg1'></span></div></div>
 <div class='card'><h4>P&amp;L según precio del subyacente <span id='t2'></span></h4>
  <div class='sub'>Curva tras los días elegidos · punteada = al vencimiento</div>
  <svg id='g2'></svg>
  <div class='leg'><span><i style='background:#2962FF'></i>Curva T+días</span>
   <span><i style='background:#8B949E'></i>Al vencimiento</span><span id='lg2'></span></div></div>
</div>
<script>
const D={data};
function erf(x){{const s=Math.sign(x);x=Math.abs(x);const t=1/(1+0.3275911*x);
 return s*(1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*Math.exp(-x*x));}}
const N=x=>0.5*(1+erf(x/Math.SQRT2));
function bs(s,k,t,v,call){{if(t<=0||v<=0)return Math.max(0,call?s-k:k-s);
 const d1=(Math.log(s/k)+(0.04+v*v/2)*t)/(v*Math.sqrt(t)),d2=d1-v*Math.sqrt(t);
 return call? s*N(d1)-k*Math.exp(-0.04*t)*N(d2) : k*Math.exp(-0.04*t)*N(-d2)-s*N(-d1);}}
const val=(c,s,d)=>bs(s,c.strike,Math.max(c.dte-Math.min(d,c.dte),0)/365,c.iv,c.tipo==='CALL');
const pnl=(c,s,d)=>(val(c,s,d)-c.prima)*100;
const C0=D.c[0],maxD=Math.max(1,...D.c.map(c=>c.dte));
let dias=Math.min(Math.max(1,D.d0),maxD),T=D.obj,first=true;
const usd=v=>(v<0?'−':'+')+'$'+Math.abs(v).toLocaleString('en-US',{{maximumFractionDigits:0}});
const $=id=>document.getElementById(id);
function ns(t,a,txt){{const e=document.createElementNS('http://www.w3.org/2000/svg',t);for(const k in a)e.setAttribute(k,a[k]);if(txt!==undefined)e.textContent=txt;return e;}}
let W=560,H=280;const P={{l:62,r:14,t:16,b:26}};
function size(svg){{W=Math.max(300,svg.clientWidth||560);H=Math.round(Math.max(230,Math.min(320,W*0.52)));svg.setAttribute('viewBox','0 0 '+W+' '+H);svg.setAttribute('height',H);}}
function frame(svg,x0,x1,y0,y1,xf){{
 const fx=x=>P.l+(x-x0)/(x1-x0)*(W-P.l-P.r),fy=y=>P.t+(y1-y)/(y1-y0)*(H-P.t-P.b);
 for(let i=0;i<=4;i++){{const y=y0+(y1-y0)*i/4;svg.appendChild(ns('line',{{x1:P.l,x2:W-P.r,y1:fy(y),y2:fy(y),stroke:'#21262D'}}));
  svg.appendChild(ns('text',{{x:P.l-6,y:fy(y)+4,'text-anchor':'end'}},usd(y)));}}
 for(let i=0;i<=3;i++){{const x=x0+(x1-x0)*i/3;svg.appendChild(ns('text',{{x:fx(x),y:H-6,'text-anchor':i===0?'start':i===3?'end':'middle'}},xf(x)));}}
 if(y0<0&&y1>0)svg.appendChild(ns('line',{{x1:P.l,x2:W-P.r,y1:fy(0),y2:fy(0),stroke:'#484F58','stroke-width':1}}));
 return [fx,fy];}}
function defs(svg,id,col){{const d=ns('defs',{{}});const g=ns('linearGradient',{{id:id,x1:0,y1:0,x2:0,y2:1}});
 g.appendChild(ns('stop',{{offset:'0%','stop-color':col,'stop-opacity':.35}}));g.appendChild(ns('stop',{{offset:'100%','stop-color':col,'stop-opacity':0}}));
 d.appendChild(g);svg.appendChild(d);}}
function path(svg,pts,attr,anim){{const d=pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+','+p[1].toFixed(1)).join('');
 const e=ns('path',Object.assign({{d:d,fill:'none'}},attr));svg.appendChild(e);
 if(anim){{const l=e.getTotalLength();e.style.setProperty('--l',l);e.classList.add('draw');}}return e;}}
function area(svg,pts,z,fill,anim){{svg.appendChild(ns('path',{{d:'M'+pts[0][0]+','+z+pts.map(p=>'L'+p[0].toFixed(1)+','+p[1].toFixed(1)).join('')+'L'+pts[pts.length-1][0]+','+z+'Z',
 fill:fill,class:anim?'fade':''}}));}}
function dot(svg,x,y,col,lbl,anchor){{svg.appendChild(ns('circle',{{cx:x,cy:y,r:9,fill:col,class:'pulse'}}));
 svg.appendChild(ns('circle',{{cx:x,cy:y,r:4.5,fill:'#0D1117',stroke:col,'stroke-width':2}}));
 if(lbl)svg.appendChild(ns('text',{{x:x+(anchor==='end'?-9:9),y:y-9,'text-anchor':anchor||'start',style:'fill:'+col,class:'tag'}},lbl));}}
function vline(svg,x,col,lbl,y,y0,y1,dash){{svg.appendChild(ns('line',{{x1:x,x2:x,y1:y0,y2:y1,stroke:col,'stroke-dasharray':dash||'3 3','stroke-opacity':.8}}));
 if(lbl)svg.appendChild(ns('text',{{x:x+4,y:y,style:'fill:'+col,class:'tag'}},lbl));}}
function draw(){{
 $('dl').value=dias+' d';$('obj').value=T.toFixed(2);
 const u=pnl(C0,T,dias),burn=(val(C0,D.spot,0)-val(C0,D.spot,dias))*100,ret=u/(C0.prima*100)*100;
 $('kp').innerHTML=`<div><span class='lbl'>Utilidad en el objetivo</span><b style='color:${{u>=0?'#26A69A':'#EF5350'}}'>${{usd(u)}}</b></div>
  <div><span class='lbl'>Retorno</span><b style='color:${{ret>=0?'#26A69A':'#EF5350'}}'>${{ret>=0?'+':''}}${{ret.toFixed(0)}}%</b></div>
  <div><span class='lbl'>Quema de theta</span><b style='color:#EF5350'>−$${{Math.abs(burn).toFixed(0)}}</b></div>`;
 $('t1').textContent='trayectoria '+dias+'d';$('t2').textContent='Black-Scholes · IV '+(C0.iv*100).toFixed(1)+'%';
 // ----- gráfico 1: P&L vs días
 const g1=$('g1');g1.innerHTML='';size(g1);defs(g1,'ga','#26A69A');
 const ds=[];const st=Math.max(0.25,maxD/120);for(let d=0;d<maxD;d+=st)ds.push(d);ds.push(maxD);
 let ys=[];D.c.forEach(c=>ds.forEach(d=>{{ys.push(pnl(c,T,d));ys.push(pnl(c,D.spot,d));}}));
 let y0=Math.min(...ys,0),y1=Math.max(...ys,0);const pd=(y1-y0)*.12||1;y0-=pd;y1+=pd;
 const [fx,fy]=frame(g1,0,maxD,y0,y1,d=>d<0.5?'Día 0':(d>=maxD-0.01?'Venc. '+Math.round(d)+'d':'Día '+Math.round(d)));
 const z=fy(0);
 D.c.forEach((c,ci)=>{{const pts=ds.map(d=>[fx(d),fy(pnl(c,T,d))]);
  if(ci===0)area(g1,pts,z,'url(#ga)',first);
  path(g1,pts,{{stroke:ci===0?'#26A69A':c.color,'stroke-width':ci===0?2.4:1.8}},first);
  if(ci===0)path(g1,ds.map(d=>[fx(d),fy(pnl(c,D.spot,d))]),{{stroke:'#EF5350','stroke-width':1.6,'stroke-dasharray':'5 4'}},false);}});
 vline(g1,fx(dias),'#2962FF',null,0,P.t,H-P.b);
 const dq=Math.max(1,Math.round(maxD*0.8));dot(g1,fx(dq),fy(pnl(C0,D.spot,dq)),'#EF5350','Quema theta',fx(dq)>W*0.6?'end':'start');
 D.c.forEach((c,ci)=>dot(g1,fx(dias),fy(pnl(c,T,dias)),ci===0?'#26A69A':c.color,ci===0?('ROI '+dias+'d '+usd(pnl(c,T,dias))):null,fx(dias)>W*0.6?'end':'start'));
 g1.onpointerdown=e=>{{g1.setPointerCapture(e.pointerId);mv(e);g1.onpointermove=mv;}};g1.onpointerup=()=>{{g1.onpointermove=null;}};
 function mv(e){{const r=g1.getBoundingClientRect();const x=(e.clientX-r.left)*W/r.width;
  dias=Math.max(1,Math.min(maxD,Math.round((x-P.l)/(W-P.l-P.r)*maxD)));draw();}}
 g1.style.cursor='grab';
 // ----- gráfico 2: P&L vs precio del subyacente
 const g2=$('g2');g2.innerHTML='';size(g2);defs(g2,'gb','#2962FF');
 const xs=[];for(let i=0;i<=140;i++)xs.push(D.lo+(D.hi-D.lo)*i/140);
 let zs=[];D.c.forEach(c=>xs.forEach(x=>{{zs.push(pnl(c,x,dias));zs.push(pnl(c,x,c.dte));}}));
 let a0=Math.min(...zs),a1=Math.max(...zs);const pa=(a1-a0)*.1||1;a0-=pa;a1+=pa;
 const [gx,gy]=frame(g2,D.lo,D.hi,a0,a1,x=>'$'+x.toFixed(0));
 const z2=gy(0);
 if(a0<0)g2.appendChild(ns('rect',{{x:P.l,y:z2,width:W-P.l-P.r,height:Math.max(0,H-P.b-z2),fill:'#EF5350',opacity:.05}}));
 if(a1>0)g2.appendChild(ns('rect',{{x:P.l,y:P.t,width:W-P.l-P.r,height:Math.max(0,z2-P.t),fill:'#26A69A',opacity:.04}}));
 D.niv.slice().sort((a,b)=>a.v-b.v).forEach((n,i)=>{{if(n.v>D.lo&&n.v<D.hi)vline(g2,gx(n.v),n.c,n.t,P.t+26+(i%3)*13,P.t,H-P.b,'2 3');}});
 vline(g2,gx(D.spot),'#E6EDF3','Spot $'+D.spot.toFixed(2),P.t+10,P.t,H-P.b,'1 0');
 const be=C0.tipo==='CALL'?C0.strike+C0.prima:C0.strike-C0.prima;
 D.c.forEach((c,ci)=>{{const col=ci===0?'#2962FF':c.color;
  path(g2,xs.map(x=>[gx(x),gy(pnl(c,x,c.dte))]),{{stroke:ci===0?'#8B949E':col,'stroke-width':1.2,'stroke-dasharray':'4 4','stroke-opacity':.8}},false);
  const pt=xs.map(x=>[gx(x),gy(pnl(c,x,dias))]);
  if(ci===0)area(g2,pt,z2,'url(#gb)',first);
  path(g2,pt,{{stroke:col,'stroke-width':ci===0?2.4:1.8}},first);}});
 if(be>D.lo&&be<D.hi)dot(g2,gx(be),gy(pnl(C0,be,dias)),'#F0B429','B/E $'+be.toFixed(2),gx(be)>W*0.6?'end':'start');
 dot(g2,gx(T),gy(pnl(C0,T,dias)),'#26A69A','Target $'+T.toFixed(2),gx(T)>W*0.6?'end':'start');
 if(C0.strike>D.lo&&C0.strike<D.hi)g2.appendChild(ns('text',{{x:gx(C0.strike),y:H-P.b-4,'text-anchor':'middle',style:'fill:#E6EDF3',class:'tag'}},'K '+C0.strike));
 $('lg1').innerHTML=D.c.slice(1).map(c=>`<i style='background:${{c.color}}'></i>${{c.nombre}}`).join(' ');
 $('lg2').innerHTML=$('lg1').innerHTML;
 first=false;
}}
const sv=Math.max(0.5,Math.round(D.spot*0.0025*2)/2);
$('dm').onclick=()=>{{dias=Math.max(1,dias-1);draw();}};$('dp').onclick=()=>{{dias=Math.min(maxD,dias+1);draw();}};
$('om').onclick=()=>{{T=T-sv;draw();}};$('op').onclick=()=>{{T=T+sv;draw();}};
$('dl').onchange=()=>{{const v=parseInt($('dl').value);if(!isNaN(v))dias=Math.max(1,Math.min(maxD,v));draw();}};
$('obj').onchange=()=>{{const v=parseFloat($('obj').value);if(!isNaN(v))T=v;draw();}};
draw();
function fit(){{try{{window.frameElement.style.height=(document.body.scrollHeight+4)+'px';}}catch(e){{}}}}
fit();[150,400,900,1600].forEach(t=>setTimeout(fit,t));
try{{new ResizeObserver(fit).observe(document.body);}}catch(e){{}}
let rt;window.addEventListener('resize',()=>{{clearTimeout(rt);rt=setTimeout(()=>{{draw();fit();}},150);}});
</script></body></html>"""
