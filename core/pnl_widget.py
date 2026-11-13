"""Gráfico P&L dinámico con punto móvil de trayectoria (time-to-target), calculado en el navegador.

Arriba: P&L de 1 contrato según el precio del subyacente cuando han pasado `días` (curva continua) y al vencimiento
(punteada), para la opción del simulador y la óptima del motor. Abajo: P&L en el precio objetivo según los días de
llegada, con un punto arrastrable (la «velocidad de llegada»). El deslizador, el punto y el precio objetivo están
sincronizados; la valoración es Black-Scholes con la IV actual (misma fórmula que `options.pnl_trayectoria`).
"""
import json

FONT = "'JetBrains Mono','Fira Code',monospace"


def html(spot: float, objetivo: float, contratos: list[dict], dias0: int, rango: tuple[float, float],
         niveles: list[dict] | None = None) -> str:
    """contratos: [{nombre, tipo, strike, iv (fracción), prima, dte, color}]."""
    data = json.dumps({"spot": spot, "obj": objetivo, "c": contratos, "d0": dias0, "lo": rango[0], "hi": rango[1],
                       "niv": niveles or []})
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@400;600&display=swap');
body{{margin:0;background:#0D1117;color:#E6EDF3;font-family:Inter,system-ui,sans-serif;font-size:12px}}
.box{{background:#161B22;border:1px solid #30363D;border-radius:6px;padding:10px 12px}}
.ctl{{display:grid;grid-template-columns:1.6fr 1fr;gap:14px;align-items:end;margin-bottom:8px}}
label{{color:#8B949E;font-size:11px;display:block;margin-bottom:4px}}
input[type=range]{{width:100%;accent-color:#2962FF}}
.num{{font-family:{FONT};font-variant-numeric:tabular-nums}}
.step{{display:flex;align-items:center;gap:0;border:1px solid #30363D;border-radius:4px;width:max-content}}
.step button{{background:#0D1117;color:#E6EDF3;border:0;width:26px;height:26px;cursor:pointer;font-size:14px}}
.step button:hover{{background:#21262D}}
.step input{{width:84px;height:24px;border:0;border-left:1px solid #30363D;border-right:1px solid #30363D;background:#0D1117;
  color:#E6EDF3;text-align:center;font-family:{FONT};font-size:12px;outline:none}}
.step input:focus{{box-shadow:inset 0 0 0 1px #2962FF}}
.mt{{display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));gap:8px;margin:6px 0 8px}}
.card{{border:1px solid #30363D;border-radius:6px;padding:7px 9px;background:#0D1117}}
.card h5{{margin:0 0 4px;font-size:11px;font-weight:600;display:flex;align-items:center;gap:6px}}
.card .r{{display:flex;justify-content:space-between;gap:8px;font-size:12px;line-height:1.55}}
.card .r span:first-child{{color:#8B949E}}
.sw{{width:10px;height:3px;border-radius:2px;display:inline-block}}
svg text{{font-family:{FONT};font-size:11px;fill:#8B949E}}
.ttl{{font-size:11px;color:#8B949E;margin:4px 0 2px}}
.grab{{cursor:grab}} .grab:active{{cursor:grabbing}}
</style></head><body><div class='box'>
<div class='ctl'>
 <div><label>Días hasta llegar al objetivo (velocidad de llegada)</label>
  <div style='display:flex;gap:10px;align-items:center'>
   <div class='step'><button id='dm'>−</button><input id='dl' class='num'><button id='dp'>+</button></div>
   <input type='range' id='dias' min='1' step='1' style='flex:1'></div></div>
 <div><label>Precio objetivo del subyacente</label>
  <div class='step'><button id='m'>−</button><input id='obj' class='num'><button id='p'>+</button></div></div>
</div>
<div class='mt' id='mt'></div>
<div class='ttl'>P&amp;L por contrato según el precio del subyacente · línea continua = tras los días elegidos · punteada = al vencimiento</div>
<svg id='g1' width='100%' height='230'></svg>
<div class='ttl'>P&amp;L en el precio objetivo según los días de llegada · arrastra el punto</div>
<svg id='g2' width='100%' height='170'></svg>
</div>
<script>
const D={data};
function erf(x){{const s=Math.sign(x);x=Math.abs(x);const t=1/(1+0.3275911*x);
 const y=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*Math.exp(-x*x);return s*y;}}
const N=x=>0.5*(1+erf(x/Math.SQRT2));
function bs(s,k,t,v,call){{if(t<=0||v<=0)return Math.max(0,call?s-k:k-s);
 const d1=(Math.log(s/k)+(0.04+v*v/2)*t)/(v*Math.sqrt(t)),d2=d1-v*Math.sqrt(t);
 return call? s*N(d1)-k*Math.exp(-0.04*t)*N(d2) : k*Math.exp(-0.04*t)*N(-d2)-s*N(-d1);}}
function pnl(c,s,dias){{const r=Math.max(c.dte-Math.min(dias,c.dte),0)/365;return (bs(s,c.strike,r,c.iv,c.tipo==='CALL')-c.prima)*100;}}
const maxD=Math.max(...D.c.map(c=>c.dte));
const sl=document.getElementById('dias'),ob=document.getElementById('obj');
sl.max=maxD;sl.value=Math.min(Math.max(1,D.d0),maxD);ob.value=D.obj.toFixed(2);
const usd=v=>(v<0?'−':'+')+'$'+Math.abs(v).toLocaleString('en-US',{{maximumFractionDigits:0}});
const col=v=>v>=0?'#26A69A':'#EF5350';
function ns(t,a){{const e=document.createElementNS('http://www.w3.org/2000/svg',t);for(const k in a)e.setAttribute(k,a[k]);return e;}}
function axes(svg,W,H,P,x0,x1,y0,y1,fx,fy,xfmt){{
 for(let i=0;i<=4;i++){{const y=y0+(y1-y0)*i/4;svg.appendChild(ns('line',{{x1:P.l,x2:W-P.r,y1:fy(y),y2:fy(y),stroke:'#21262D'}}));
  const t=ns('text',{{x:4,y:fy(y)+4}});t.textContent=usd(y);svg.appendChild(t);}}
 for(let i=0;i<=5;i++){{const x=x0+(x1-x0)*i/5;const t=ns('text',{{x:fx(x),y:H-4,'text-anchor':'middle'}});t.textContent=xfmt(x);svg.appendChild(t);}}
 if(y0<0&&y1>0)svg.appendChild(ns('line',{{x1:P.l,x2:W-P.r,y1:fy(0),y2:fy(0),stroke:'#484F58'}}));}}
function draw(){{
 const dias=+sl.value,T=+ob.value;document.getElementById('dl').value=dias+' d';
 // métricas
 const mt=document.getElementById('mt');mt.style.setProperty('--n',D.c.length);mt.innerHTML='';
 D.c.forEach(c=>{{const d=Math.min(dias,c.dte),u=pnl(c,T,d),ret=u/(c.prima*100)*100;
  const burn=(bs(D.spot,c.strike,c.dte/365,c.iv,c.tipo==='CALL')-bs(D.spot,c.strike,Math.max(c.dte-d,0)/365,c.iv,c.tipo==='CALL'))*100;
  mt.insertAdjacentHTML('beforeend',`<div class='card'><h5><span class='sw' style='background:${{c.color}}'></span>${{c.nombre}}</h5>
  <div class='r'><span>Utilidad proyectada en el objetivo</span><b class='num' style='color:${{col(u)}}'>${{usd(u)}}</b></div>
  <div class='r'><span>Retorno estimado</span><b class='num' style='color:${{col(ret)}}'>${{ret>=0?'+':''}}${{ret.toFixed(0)}}%</b></div>
  <div class='r'><span>Costo por tiempo (quema de theta)</span><b class='num' style='color:#EF5350'>−$${{Math.abs(burn).toLocaleString('en-US',{{maximumFractionDigits:0}})}}</b></div>
  <div class='r'><span>Prima pagada</span><b class='num'>$${{(c.prima*100).toLocaleString('en-US',{{maximumFractionDigits:0}})}}</b></div></div>`);}});
 // gráfico 1: P&L vs precio
 const g1=document.getElementById('g1');g1.innerHTML='';const W=g1.clientWidth,H=230,P={{l:62,r:12,t:10,b:20}};
 const xs=[];for(let i=0;i<=120;i++)xs.push(D.lo+(D.hi-D.lo)*i/120);
 let ys=[];D.c.forEach(c=>xs.forEach(x=>{{ys.push(pnl(c,x,Math.min(dias,c.dte)));ys.push(pnl(c,x,c.dte));}}));
 let y0=Math.min(...ys),y1=Math.max(...ys);const pad=(y1-y0)*0.08||1;y0-=pad;y1+=pad;
 const fx=x=>P.l+(x-D.lo)/(D.hi-D.lo)*(W-P.l-P.r),fy=y=>P.t+(y1-y)/(y1-y0)*(H-P.t-P.b);
 axes(g1,W,H,P,D.lo,D.hi,y0,y1,fx,fy,x=>'$'+x.toFixed(0));
 D.niv.slice().sort((a,b)=>a.v-b.v).forEach((n,i)=>{{if(n.v<D.lo||n.v>D.hi)return;g1.appendChild(ns('line',{{x1:fx(n.v),x2:fx(n.v),y1:P.t,y2:H-P.b,stroke:n.c,'stroke-dasharray':'2 3','stroke-opacity':.7}}));
  const t=ns('text',{{x:fx(n.v)+3,y:H-P.b-18-(i%3)*13,style:'fill:'+n.c}});t.textContent=n.t+' '+n.v.toFixed(0);g1.appendChild(t);}});
 g1.appendChild(ns('line',{{x1:fx(D.spot),x2:fx(D.spot),y1:P.t,y2:H-P.b,stroke:'#8B949E'}}));
 const ts=ns('text',{{x:fx(D.spot)+3,y:H-P.b-4}});ts.textContent='spot';g1.appendChild(ts);
 D.c.forEach(c=>{{const pe=xs.map((x,i)=>(i?'L':'M')+fx(x).toFixed(1)+','+fy(pnl(c,x,c.dte)).toFixed(1)).join('');
  g1.appendChild(ns('path',{{d:pe,fill:'none',stroke:c.color,'stroke-width':1,'stroke-dasharray':'4 3','stroke-opacity':.7}}));
  const pt=xs.map((x,i)=>(i?'L':'M')+fx(x).toFixed(1)+','+fy(pnl(c,x,Math.min(dias,c.dte))).toFixed(1)).join('');
  g1.appendChild(ns('path',{{d:pt,fill:'none',stroke:c.color,'stroke-width':2}}));
  const u=pnl(c,T,Math.min(dias,c.dte));g1.appendChild(ns('circle',{{cx:fx(T),cy:fy(u),r:5,fill:'#0D1117',stroke:c.color,'stroke-width':2}}));}});
 g1.appendChild(ns('line',{{x1:fx(T),x2:fx(T),y1:P.t,y2:H-P.b,stroke:'#F0B429','stroke-dasharray':'3 3'}}));
 const to=ns('text',{{x:fx(T)+3,y:P.t+22,style:'fill:#F0B429'}});to.textContent='objetivo $'+T.toFixed(2);g1.appendChild(to);
 // gráfico 2: P&L en el objetivo vs días de llegada (punto arrastrable)
 const g2=document.getElementById('g2');g2.innerHTML='';const H2=170,P2={{l:62,r:12,t:10,b:20}};
 const ds=[];for(let d=1;d<=maxD;d++)ds.push(d);
 let zs=[];D.c.forEach(c=>ds.forEach(d=>zs.push(pnl(c,T,Math.min(d,c.dte)))));
 let z0=Math.min(...zs),z1=Math.max(...zs);const pz=(z1-z0)*0.1||1;z0-=pz;z1+=pz;
 const gx=d=>P2.l+(d-1)/Math.max(maxD-1,1)*(W-P2.l-P2.r),gy=z=>P2.t+(z1-z)/(z1-z0)*(H2-P2.t-P2.b);
 axes(g2,W,H2,P2,1,maxD,z0,z1,gx,gy,d=>Math.round(d)+'d');
 D.c.forEach(c=>{{const p=ds.map((d,i)=>(i?'L':'M')+gx(d).toFixed(1)+','+gy(pnl(c,T,Math.min(d,c.dte))).toFixed(1)).join('');
  g2.appendChild(ns('path',{{d:p,fill:'none',stroke:c.color,'stroke-width':2}}));}});
 g2.appendChild(ns('line',{{x1:gx(dias),x2:gx(dias),y1:P2.t,y2:H2-P2.b,stroke:'#2962FF','stroke-dasharray':'3 3'}}));
 D.c.forEach(c=>{{const dot=ns('circle',{{cx:gx(dias),cy:gy(pnl(c,T,Math.min(dias,c.dte))),r:7,fill:c.color,stroke:'#0D1117','stroke-width':2,class:'grab'}});
  g2.appendChild(dot);}});
 // arrastre: cualquier punto del gráfico inferior mueve la velocidad de llegada
 g2.onpointerdown=e=>{{g2.setPointerCapture(e.pointerId);mv(e);g2.onpointermove=mv;}};
 g2.onpointerup=e=>{{g2.onpointermove=null;}};
 function mv(e){{const r=g2.getBoundingClientRect();const x=e.clientX-r.left;
  const d=Math.round(1+(x-P2.l)/(W-P2.l-P2.r)*(maxD-1));sl.value=Math.max(1,Math.min(maxD,d));draw();}}
}}
sl.oninput=draw;ob.onchange=draw;
const dl=document.getElementById('dl');
dl.onchange=()=>{{const v=parseInt(dl.value);if(!isNaN(v))sl.value=Math.max(1,Math.min(maxD,v));draw();}};
document.getElementById('dm').onclick=()=>{{sl.value=Math.max(1,+sl.value-1);draw();}};
document.getElementById('dp').onclick=()=>{{sl.value=Math.min(maxD,+sl.value+1);draw();}};
const stepv=Math.max(0.5,Math.round(D.spot*0.0025*2)/2);
document.getElementById('m').onclick=()=>{{ob.value=(+ob.value-stepv).toFixed(2);draw();}};
document.getElementById('p').onclick=()=>{{ob.value=(+ob.value+stepv).toFixed(2);draw();}};
window.addEventListener('resize',draw);draw();
</script></body></html>"""
