"""Gráfico «Comparativa de las 3 opciones» de la pestaña Opciones, con el mismo estilo que los gráficos de P&L
(pnl_widget): fondo #0D1117, rejilla sutil, líneas que se dibujan al cargar, puntos con halo animado y números en
JetBrains Mono.

Eje X = fecha (de hoy al vencimiento más lejano) · eje Y = precio del subyacente.
Cada opción: camino punteado desde el precio actual hasta su strike en su vencimiento, punto en (vencimiento, strike),
triángulo en el breakeven y una franja entre ambos (lo que cuesta la prima en precio). Líneas de referencia: precio
actual y objetivo. La opción elegida lleva el halo animado.
"""
import json

FONT = "'JetBrains Mono','Fira Code',monospace"
COLORES = {1: "#4C8DF6", 2: "#D29922", 3: "#39C5CF"}  # azul, ámbar, cian: ni verde ni rojo (esos dicen alza/baja)


def html(spot: float, objetivo: float | None, opciones: dict, elegida: int, hoy: str) -> str:
    """opciones: {1: dict|None, 2: …, 3: …} con strike, tipo, vencimiento (texto), exp_iso (AAAA-MM-DD), dte,
    breakeven, ve, pop, prima, costo, delta."""
    ops = []
    for t in (1, 2, 3):
        o = opciones.get(t)
        if not o:
            continue
        ops.append({"t": t, "c": COLORES[t], "k": o["strike"], "tipo": o["tipo"], "venc": o["vencimiento"],
                    "f": o["exp_iso"], "dte": o["dte"], "be": o["breakeven"], "ve": o["ve"], "pop": o["pop"],
                    "prima": o["prima"], "costo": o["costo"], "delta": o.get("delta") or 0})
    data = json.dumps({"spot": spot, "obj": objetivo, "ops": ops, "sel": elegida, "hoy": hoy})
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@400;600&display=swap');
*{{box-sizing:border-box}}
body{{margin:0;background:transparent;color:#E6EDF3;font-family:Inter,system-ui,sans-serif;font-size:12px}}
.card{{background:#0D1117;border:1px solid #30363D;border-radius:6px;padding:10px 10px 6px}}
.card h4{{margin:0;font-size:12px;font-weight:600;color:#E6EDF3;display:flex;justify-content:space-between;gap:8px}}
.card h4 span{{color:#8B949E;font-weight:400;font-size:11px}}
.sub{{color:#8B949E;font-size:11px;margin:2px 0 4px}}
svg{{width:100%;display:block;overflow:visible}}
svg text{{font-family:{FONT};font-size:11px;fill:#8B949E}}
.leg{{display:flex;flex-direction:column;gap:4px;font-size:11px;color:#8B949E;margin-top:6px}}
.leg i{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:-1px}}
.leg b{{font-family:{FONT};font-weight:400;color:#E6EDF3;font-variant-numeric:tabular-nums}}
.draw{{stroke-dasharray:var(--l);stroke-dashoffset:var(--l);animation:dr 1.4s ease-out forwards}}
@keyframes dr{{to{{stroke-dashoffset:0}}}}
.fade{{opacity:0;animation:fd 1s .6s ease-out forwards}}
@keyframes fd{{to{{opacity:1}}}}
.pulse{{animation:pl 1.6s ease-in-out infinite;transform-box:fill-box;transform-origin:center}}
@keyframes pl{{0%,100%{{opacity:.3;transform:scale(1)}}50%{{opacity:.85;transform:scale(1.7)}}}}
</style></head><body>
<div class='card'><h4>Comparativa de las 3 opciones <span id='t'></span></h4>
 <div class='sub'>Strike contra vencimiento · triángulo = breakeven · punteada = camino desde el precio actual</div>
 <svg id='g'></svg><div class='leg' id='leg'></div></div>
<script>
const D={data};
const $=id=>document.getElementById(id);
function ns(t,a,txt){{const e=document.createElementNS('http://www.w3.org/2000/svg',t);for(const k in a)e.setAttribute(k,a[k]);if(txt!==undefined)e.textContent=txt;return e;}}
const day=s=>new Date(s+'T12:00:00');
const fmt=d=>String(d.getDate()).padStart(2,'0')+'/'+String(d.getMonth()+1).padStart(2,'0');
function draw(){{
 const g=$('g');g.innerHTML='';
 const W=Math.max(320,g.clientWidth||560),H=Math.round(Math.max(260,Math.min(360,W*0.62)));
 g.setAttribute('viewBox','0 0 '+W+' '+H);g.setAttribute('height',H);
 const P={{l:56,r:16,t:14,b:30}};
 if(!D.ops.length){{g.appendChild(ns('text',{{x:W/2,y:H/2,'text-anchor':'middle'}},'Sin opciones que comparar'));return;}}
 const t0=day(D.hoy).getTime(),t1=Math.max(...D.ops.map(o=>day(o.f).getTime()))+2*864e5;
 const ys=[D.spot,...D.ops.map(o=>o.k),...D.ops.map(o=>o.be)];if(D.obj)ys.push(D.obj);
 let lo=Math.min(...ys),hi=Math.max(...ys);const pad=(hi-lo||D.spot*0.02)*0.12;lo-=pad;hi+=pad;
 const X=ms=>P.l+(ms-t0)/(t1-t0)*(W-P.l-P.r),Y=v=>P.t+(hi-v)/(hi-lo)*(H-P.t-P.b);
 for(let i=0;i<=4;i++){{const v=lo+(hi-lo)*i/4,y=Y(v);
  g.appendChild(ns('line',{{x1:P.l,x2:W-P.r,y1:y,y2:y,stroke:'#21262D'}}));
  g.appendChild(ns('text',{{x:P.l-6,y:y+4,'text-anchor':'end'}},'$'+v.toFixed(v>=100?0:2)));}}
 const nT=Math.max(2,Math.min(7,Math.floor((W-P.l-P.r)/70)));
 for(let i=0;i<=nT;i++){{const ms=t0+(t1-t0)*i/nT,x=X(ms);
  g.appendChild(ns('line',{{x1:x,x2:x,y1:P.t,y2:H-P.b,stroke:'#161B22'}}));
  g.appendChild(ns('text',{{x:x,y:H-P.b+16,'text-anchor':'middle'}},fmt(new Date(ms))));}}
 function ref(v,col,lbl,dash){{const y=Y(v);g.appendChild(ns('line',{{x1:P.l,x2:W-P.r,y1:y,y2:y,stroke:col,'stroke-dasharray':dash,'stroke-opacity':.85}}));
  g.appendChild(ns('text',{{x:W-P.r,y:y-5,'text-anchor':'end',fill:col}},lbl));}}
 ref(D.spot,'#8B949E','Spot $'+D.spot.toFixed(2),'4 4');
 const put=D.ops[0].tipo==='PUT';
 if(D.obj)ref(D.obj,put?'#EF5350':'#26A69A','Objetivo $'+D.obj.toFixed(2),'2 4');
 const xs=X(t0),ys0=Y(D.spot);
 g.appendChild(ns('circle',{{cx:xs,cy:ys0,r:4,fill:'#E6EDF3'}}));
 const etiquetas=[];
 D.ops.forEach(o=>{{const x=X(day(o.f).getTime()),y=Y(o.k),yb=Y(o.be);
  g.appendChild(ns('rect',{{x:x-5,y:Math.min(y,yb),width:10,height:Math.max(2,Math.abs(yb-y)),fill:o.c,'fill-opacity':.18,rx:2}}));
  const cx=(xs+x)/2,cy=ys0;const e=ns('path',{{d:'M'+xs+','+ys0+' Q'+cx+','+cy+' '+x+','+y,fill:'none',stroke:o.c,'stroke-width':o.t===D.sel?2:1.4,'stroke-opacity':o.t===D.sel?1:.7}});
  g.appendChild(e);const l=e.getTotalLength();e.style.setProperty('--l',l);e.classList.add('draw');
  e.setAttribute('stroke-dasharray','5 4');
  const tri=ns('path',{{d:'M'+(x-5)+','+(yb+(put?-4:4))+' L'+(x+5)+','+(yb+(put?-4:4))+' L'+x+','+(yb+(put?4:-4))+'Z',fill:o.c,class:'fade'}});
  tri.appendChild(ns('title',{{}},'OPT'+o.t+' breakeven $'+o.be.toFixed(2)));g.appendChild(tri);
  if(o.t===D.sel)g.appendChild(ns('circle',{{cx:x,cy:y,r:9,fill:o.c,class:'pulse'}}));
  const dot=ns('circle',{{cx:x,cy:y,r:6,fill:o.c,stroke:'#0D1117','stroke-width':1.5,class:'fade'}});
  dot.appendChild(ns('title',{{}},'OPT'+o.t+' · $'+o.k+' '+o.tipo[0]+' · '+o.venc+' · '+o.dte+' DTE\\nPrima $'+o.prima.toFixed(2)+
   ' · costo $'+o.costo.toFixed(0)+' · delta '+o.delta.toFixed(2)+'\\nProb. éxito '+o.pop.toFixed(0)+'% · VE '+(o.ve>=0?'+':'')+o.ve.toFixed(1)+'%'));
  g.appendChild(dot);
  etiquetas.push({{x:x,y:y,o:o}});}});
 etiquetas.sort((a,b)=>a.y-b.y);let last=-1e9;
 etiquetas.forEach(e=>{{let yl=Math.max(e.y+4,last+15);last=yl;const izq=e.x>W-170;
  const tx=ns('text',{{x:izq?e.x-16:e.x+16,y:yl,'text-anchor':izq?'end':'start',fill:'#E6EDF3',class:'fade'}},
   'OPT'+e.o.t+' $'+e.o.k);
  g.appendChild(tx);}});
 $('t').textContent=D.ops[0].tipo;
 $('leg').innerHTML=D.ops.map(o=>"<span><i style='background:"+o.c+"'></i>OPT"+o.t+" <b>$"+o.k+" "+o.tipo[0]+"</b> · "+o.venc+
  " · prima <b>$"+o.prima.toFixed(2)+"</b> · VE <b>"+(o.ve>=0?"+":"")+o.ve.toFixed(1)+"%</b> · éxito <b>"+o.pop.toFixed(0)+
  "%</b>"+(o.t===D.sel?" · elegida":"")+"</span>").join('');
}}
draw();
let rt;window.addEventListener('resize',()=>{{clearTimeout(rt);rt=setTimeout(draw,120);}});
function fit(){{try{{window.frameElement.style.height=(document.body.scrollHeight+4)+'px';}}catch(e){{}}}}
setTimeout(fit,50);
</script></body></html>"""
