/* Offline visualization: hypothetical house response, never boiler commands. */
(function(root) {
"use strict";
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const $=id=>document.getElementById(id);
const fixed=n=>Number(n).toFixed(1).replace(".",",");
function parts(s,outdoor=s.outdoor) {
 const base=s.target+s.slope*(s.target-outdoor), correction=s.kp*(s.target-s.room);
 return {base,correction,raw:base+correction,limited:clamp(base+correction,s.flowMin,s.flowMax)};
}
function controller(s) {
 let previous=false,integral=0,last=null;
 return function({time,room,outdoor,valid=true}) {
  if(s.mode!=="heat"||!valid||!Number.isFinite(room)||!Number.isFinite(outdoor)||room< -20||room>60||outdoor< -50||outdoor>60) {
   previous=false;integral=0;last=time;return {flow:null,demand:false,integral,reason:"Ongeldige sensor of verwarming uit"};
  }
  const h=Number.isFinite(s.hysteresis)?clamp(s.hysteresis,0.1,1.5):0.2;
  const demand=previous?room<s.target+h:room<s.target-h;
  if(!demand){previous=false;integral=0;last=time;return {flow:null,demand:false,integral,reason:"Doeltemperatuur bereikt"};}
  const dt=last===null?0:clamp(time-last,0,300);
  integral=clamp(integral+(s.target-room)*s.ki*dt,-5,5);
  previous=true;last=time;
  const flow=parts({...s,room},outdoor).raw+integral;
  return {flow:Math.round(clamp(flow,s.flowMin,s.flowMax)*100)/100,demand:true,integral,reason:"Gesimuleerde warmtevraag"};
 };
}
function simulate(s,scenario,hours,gate={},roomOptions={},pumpOptions={}) {
 // An offline, synthetic water-loop model, NOT physical burner/pump control.
 // A simulated circulating pump can continue while virtual CV permission is OFF.
 // Real BAI ReturnTemp is not trustworthy as a loop temperature without circulation.
 const configured={...s};
 if(Number.isFinite(roomOptions.target))configured.target=roomOptions.target;
 if(Number.isFinite(roomOptions.hysteresis))configured.hysteresis=roomOptions.hysteresis;
 const evaluate=controller(configured),data=[];
 let room=Number.isFinite(roomOptions.start)?roomOptions.start:
  scenario==="target"?configured.target-0.8:scenario==="cold"?Math.min(s.room,configured.target-2):s.room;
 let measured=Number.isFinite(gate.supplyStart)?clamp(gate.supplyStart,20,80):
  Number.isFinite(gate.measured)?clamp(gate.measured,20,80):45;
 let measuredReturn=Number.isFinite(gate.returnStart)?clamp(gate.returnStart,15,75):35;
 measuredReturn=clamp(measuredReturn,room,measured);
 let allowed=false,starts=0,stops=0,previousAllowed=false;
 let lastRoomDemandAt=-Infinity, pumpTransitions=0, previousPump=false;
 const pumpMode=["room","room-postrun","release"].includes(pumpOptions.mode)?
  pumpOptions.mode:"room";
 const gateEnabled=gate.enabled===true;
 const thresholdsValid=Number.isFinite(gate.startAt)&&Number.isFinite(gate.stopAt)&&
   gate.startAt>=20&&gate.stopAt<=75&&gate.startAt+0.5<=gate.stopAt;
 for(let n=0;n<=hours*12;n++){
  const h=n/12;
  const outdoor=scenario==="cold"?-5+2*Math.sin(h*Math.PI/12):scenario==="sunny"?3+Math.min(h,8)*1.5:s.outdoor;
  const valid=s.roomValid&&s.outdoorValid&&!(scenario==="fault"&&h>=2);
  const result=evaluate({time:n*300,room,outdoor,valid});
  if(result.demand)lastRoomDemandAt=n*300;
  const pumpOn=pumpMode==="release"?previousAllowed:
   pumpMode==="room-postrun"?(result.demand||n*300-lastRoomDemandAt<=2700):result.demand;
  if(pumpOn!==previousPump)pumpTransitions++;
  previousPump=pumpOn;
  // The controller may only trust ReturnTemp when the loop is circulating.
  // In 'release' mode with a return gate this can intentionally show a
  // deadlock: no circulation => no credible return reading => no CV restart.
  const returnSensorValid=valid&&pumpOn&&gate.valid!==false&&Number.isFinite(measuredReturn);
  const gateDecision=gateEnabled?returnGate(allowed,{
   roomDemand:result.demand,measuredReturn,sensorValid:returnSensorValid&&thresholdsValid,
   startAt:gate.startAt,stopAt:gate.stopAt
  }):{allowed:result.demand,reason:result.reason};
  allowed=gateDecision.allowed;
  if(allowed&&!previousAllowed)starts++;
  if(!allowed&&previousAllowed)stops++;
  previousAllowed=allowed;
  data.push({
   h,room,outdoor,target:configured.target,flow:result.flow,
   measuredFlow:valid?measured:null,
   // A real return probe still reports local boiler temperature with pump OFF;
   // only the suitability for controlling the entire circuit is different.
   measuredReturn:valid&&gate.valid!==false?measuredReturn:null,
   returnCirculating:pumpOn,
   roomDemand:result.demand,demand:allowed,cvAllowed:allowed,
   pumpOn,pumpMode,pumpTransitions,
   integral:result.integral,valid,returnSensorValid,
   gateReason:gateDecision.reason,reason:result.reason,starts,stops
  });
  if(n<hours*12){
   // Intentionally fictional two-node water loop. With pump circulation
   // and CV permission off, radiator heat keeps leaving the circuit;
   // without circulation, boiler-local sensor temperatures change slowly.
   // There is no modeled actual burner flame, d.2 blocking or pump power draw.
   const beforeSupply=measured;
   const beforeReturn=measuredReturn;
   if(allowed&&pumpOn&&Number.isFinite(result.flow)) {
    measured+=clamp((result.flow-measured)*0.46,-2,4);
   } else if(pumpOn) {
    measured+=clamp((measuredReturn-measured)*0.19,-3,0);
   } else {
    measured+=clamp((measuredReturn-measured)*0.015,-0.45,0);
   }
   const radiatorDelta=clamp(4+0.26*Math.max(0,measured-room),3,18);
   const returnTarget=allowed&&pumpOn?Math.max(room,measured-radiatorDelta):room;
   const returnRate=pumpOn?(allowed?0.22:0.14):0.02;
   measuredReturn+=clamp((returnTarget-measuredReturn)*returnRate,-2.5,2.5);
   measured=clamp(measured,room,85);
   measuredReturn=clamp(measuredReturn,room,measured);
   const transferWater=(beforeSupply+beforeReturn+measured+measuredReturn)/4;
   const radiatorFactor=pumpOn?(allowed?1:0.35):0.05;
   const radiatorGain=Math.max(0,transferWater-room)*0.08*radiatorFactor;
   const outdoorLoss=0.045*(room-outdoor);
   room=clamp(room+(radiatorGain-outdoorLoss)/12,-20,60);
  }
 }
 return data;
}
function line(data,project) {
 let str="",active=false;
 for(const p of data){const v=project(p);
  // project() returns an [x, y] coordinate, not a single scalar.
  // The previous Number.isFinite(v) rejected every coordinate pair, leaving SVG paths empty.
  if(!Array.isArray(v)||v.length!==2||!v.every(Number.isFinite)){active=false;continue;}
  str+=(active?" L":"M")+v.map(n=>n.toFixed(1)).join(",");active=true;
 }
 return str;
}
function compare(svg,s){
 const X=t=>56+(t+20)/50*630,Y=t=>285-(t-20)/65*248;
 const data=Array.from({length:101},(_,i)=>-20+i/2);
 const axes=[];
 for(let y=20;y<=80;y+=10)axes.push('<line class="chart-grid-line" x1="56" x2="686" y1="'+Y(y)+'" y2="'+Y(y)+'"/><text class="chart-label" x="45" y="'+(Y(y)+4)+'" text-anchor="end">'+y+'°</text>');
 for(let x=-20;x<=30;x+=10)axes.push('<text class="chart-label" x="'+X(x)+'" y="313" text-anchor="middle">'+x+'°</text>');
 const path=(fn,cls)=>'<path class="'+cls+'" d="'+line(data,x=>[X(x),Y(clamp(fn(parts(s,x)),20,85))])+'"/>';
 const chosen=parts(s);const xx=X(clamp(s.outdoor,-20,30));
 svg.innerHTML=axes.join("")+path(p=>p.base,"curve-base-line")+path(p=>p.raw,"curve-room-line")+path(p=>p.limited,"curve-bound-line")+
 (s.roomValid&&s.outdoorValid?'<line class="chart-marker-vline" x1="'+xx+'" x2="'+xx+'" y1="37" y2="285"/><circle class="chart-marker" cx="'+xx+'" cy="'+Y(chosen.limited)+'" r="6"/>':"");
}
function timeline(svg,data,index,hours) {
 const X=h=>56+h/hours*630;
 const roomValues=data.map(p=>p.room).concat(data[0].target);
 const roomLow=Math.floor(Math.min(...roomValues)-0.75);
 const roomHigh=Math.max(roomLow+3,Math.ceil(Math.max(...roomValues)+0.75));
 // Requested and simulated measured supply share the SAME lower temperature axis.
 const flowValues=data.flatMap(p=>[p.flow,p.measuredFlow,p.measuredReturn]).filter(Number.isFinite);
 const flowLow=flowValues.length?Math.max(0,Math.floor((Math.min(...flowValues)-3)/5)*5):20;
 const flowHigh=flowValues.length?Math.max(flowLow+15,Math.ceil((Math.max(...flowValues)+3)/5)*5):85;
 const RY=v=>150-(v-roomLow)/(roomHigh-roomLow)*109;
 const FY=v=>303-(v-flowLow)/(flowHigh-flowLow)*83;
 const axes=[];
 axes.push('<text class="sim-axis-title" x="56" y="20">KAMER / DOEL (°C)</text>');
 axes.push('<text class="sim-axis-title" x="56" y="171">AANVOER EN RETOUR: FICTIEF (°C)</text>');
 for(let j=0;j<=4;j++){
  const rt=roomLow+(roomHigh-roomLow)*j/4;
  const ry=RY(rt);
  const ft=flowLow+(flowHigh-flowLow)*j/4;
  const fy=FY(ft);
  axes.push('<line class="chart-grid-line" x1="56" x2="686" y1="'+ry+'" y2="'+ry+'"/>');
  axes.push('<text class="chart-label" x="45" y="'+(ry+4)+'" text-anchor="end">'+fixed(rt)+'°</text>');
  axes.push('<line class="chart-grid-line" x1="56" x2="686" y1="'+fy+'" y2="'+fy+'"/>');
  axes.push('<text class="chart-label" x="45" y="'+(fy+4)+'" text-anchor="end">'+fixed(ft)+'°</text>');
 }
 for(let t=0;t<=hours;t+=hours/6)
  axes.push('<text class="chart-label" x="'+X(t)+'" y="330" text-anchor="middle">'+t+'u</text>');
 const path=(field,y,cls)=>'<path class="'+cls+'" d="'+line(data,p=>
  Number.isFinite(p[field])?[X(p.h),y(p[field])]:null)+'"/>';
 const bands=(field,y,cls)=>{
  const results=[];let begin=null;
  for(let i=0;i<data.length;i++){
   if(data[i][field]&&begin===null)begin=data[i].h;
   if(begin!==null&&(!data[i][field]||i===data.length-1)){
    const end=data[i][field]?hours:data[i].h;
    if(end>begin)results.push('<rect class="'+cls+'" x="'+X(begin)+'" y="'+y+'" width="'+(X(end)-X(begin))+'" height="6"/>');
    begin=null;
   }
  }
  return results.join("");
 };
 axes.push('<rect class="sim-room-track" x="56" y="181" width="630" height="6"/>');
 axes.push('<rect class="sim-demand-track" x="56" y="193" width="630" height="6"/>');
 axes.push('<rect class="sim-pump-track" x="56" y="205" width="630" height="6"/>');
 // Draw the same physically present return reading with two visual styles.
 // Each two-point segment is drawn once: solid when circulating, dashed
 // when the probe only represents standing water local to the boiler.
 const returnSegments=(circulating,cls)=>{
  let d="";
  for(let i=1;i<data.length;i++){
   const prev=data[i-1],next=data[i];
   if(!Number.isFinite(prev.measuredReturn)||!Number.isFinite(next.measuredReturn))continue;
   const useSolid=Boolean(prev.pumpOn||next.pumpOn);
   if(useSolid!==circulating)continue;
   d+="M"+X(prev.h).toFixed(1)+","+FY(prev.measuredReturn).toFixed(1)+
      "L"+X(next.h).toFixed(1)+","+FY(next.measuredReturn).toFixed(1)+" ";
  }
  return '<path class="'+cls+'" d="'+d.trim()+'"/>';
 };
 const cursor=X(data[index].h);
 const currentMeasured=data[index].measuredFlow;
 const currentReturn=data[index].measuredReturn;
 svg.innerHTML=axes.join("")+
  bands("roomDemand",181,"sim-room-demand-band")+
  bands("demand",193,"sim-demand-band")+
  bands("pumpOn",205,"sim-pump-band")+
  path("target",RY,"curve-base-line")+path("room",RY,"curve-room-line")+
  path("flow",FY,"curve-bound-line")+path("measuredFlow",FY,"sim-measured-line")+
  returnSegments(true,"sim-return-line")+
  returnSegments(false,"sim-return-stagnant-line")+
  '<line class="chart-marker-vline" x1="'+cursor+'" x2="'+cursor+'" y1="41" y2="150"/>'+
  '<line class="chart-marker-vline" x1="'+cursor+'" x2="'+cursor+'" y1="181" y2="303"/>'+
  '<circle class="sim-room-cursor" cx="'+cursor+'" cy="'+RY(data[index].room)+'" r="4.8"/>'+
  (Number.isFinite(currentMeasured)?'<circle class="sim-flow-cursor" cx="'+cursor+'" cy="'+FY(currentMeasured)+'" r="4.8"/>':"")+
  (Number.isFinite(currentReturn)?'<circle class="sim-return-cursor" cx="'+cursor+'" cy="'+FY(currentReturn)+'" r="4.8"/>':"");
}
// Experimental VIRTUAL CH permission using RETURN temperature.
// Requires credible, fresh BAI ReturnTemp while pump circulation is present.
// Never a gas-burner, combustion, pump, or thermostat write command.
function returnGate(previousAllowed, {roomDemand,measuredReturn,sensorValid=true,startAt,stopAt}) {
 if(!roomDemand) return {allowed:false,reason:"Geen kamervraag: CV-aanvraag geblokkeerd"};
 if(!sensorValid||!Number.isFinite(measuredReturn)||measuredReturn<0||measuredReturn>100)
  return {allowed:false,reason:"Retourtemperatuur ongeldig: CV-aanvraag geblokkeerd"};
 if(!Number.isFinite(startAt)||!Number.isFinite(stopAt)||startAt>=stopAt)
  return {allowed:false,reason:"Ongeldige retourhysterese"};
 if(previousAllowed){
  return measuredReturn>=stopAt?
   {allowed:false,reason:"Retour boven stopgrens: CV-vrijgave uit"}:
   {allowed:true,reason:"Retourhysterese houdt CV-vrijgave aan"};
 }
 return measuredReturn<=startAt?
  {allowed:true,reason:"Retour voldoende afgekoeld: CV-vrijgave aan"}:
  {allowed:false,reason:"Wachten totdat de retour voldoende afgekoeld is"};
}
const returnSettings={enabled:false,returnStart:35,supplyStart:45,startAt:30,stopAt:42,valid:true};
const pumpSettings={mode:"room-postrun"};
// Independent from the real HA/demo thermostat: users may explore any initial
// room temperature and target without writing to the real or mock HA climate.
const roomSettings={start:null,target:null,hysteresis:0.2,customStart:false};
function defaultRoomStart(s,scenario,target){
 if(scenario==="target")return clamp(target-0.8,10,30);
 if(scenario==="cold")return clamp(Math.min(s.room,target-2),10,30);
 if(scenario==="sunny")return clamp(target-1.5,10,30);
 return clamp(s.room,10,30);
}
function updateRoomInputs(){
 for(const [id,key] of [["sim-room-start","start"],["sim-room-target","target"],["sim-room-hysteresis","hysteresis"]]){
  $(id).value=roomSettings[key].toFixed(1);
 }
}
function initRoomInputs(){
 const s=readState();
 roomSettings.target=clamp(s.target,16,27);
 roomSettings.start=defaultRoomStart(s,$("sim-scenario").value,roomSettings.target);
 updateRoomInputs();
 const limits={start:[10,30],target:[16,27],hysteresis:[0.1,1.5]};
 const change=(id,key)=>{
  $(id).addEventListener("input",e=>{
   const value=e.target.value===""?NaN:Number(e.target.value);
   const [lo,hi]=limits[key];
   if(!Number.isFinite(value)||value<lo||value>hi){
    $("sim-room-settings-status").textContent="Waarde buiten bereik. Kies "+lo+"–"+hi+" °C.";
    return;
   }
   roomSettings[key]=value;
   if(key==="start")roomSettings.customStart=true;
   if(key==="target"&&!roomSettings.customStart)
    roomSettings.start=defaultRoomStart(readState(),$("sim-scenario").value,value);
   // Do not change a currently typed number field while it has focus.
   if(key==="target"&&!roomSettings.customStart)
    $("sim-room-start").value=roomSettings.start.toFixed(1);
   $("sim-room-settings-status").textContent="Simulatie bijgewerkt; geen echte kamerinstellingen veranderd.";
   updateReturnGate(readState());
   if(view==="sim")run(Number($("sim-cursor").value));
  });
 };
 for(const [id,key] of [["sim-room-start","start"],["sim-room-target","target"],["sim-room-hysteresis","hysteresis"]])change(id,key);
 $("sim-room-reset").addEventListener("click",()=>{
  roomSettings.target=clamp(readState().target,16,27);
  roomSettings.hysteresis=0.2;
  roomSettings.customStart=false;
  roomSettings.start=defaultRoomStart(readState(),$("sim-scenario").value,roomSettings.target);
  updateRoomInputs();
  $("sim-room-settings-status").textContent="Scenario-beginwaarden hersteld.";
  updateReturnGate(readState());
  if(view==="sim")run(Number($("sim-cursor").value));
 });
}
function updateReturnGate(s) {
 const ok=Number.isFinite(returnSettings.startAt)&&Number.isFinite(returnSettings.stopAt)&&
  returnSettings.startAt>=20&&returnSettings.stopAt<=75&&
  returnSettings.startAt+0.5<=returnSettings.stopAt;
 $("return-gate-error").textContent=ok?"":"Retourgrenzen ongeldig: kies inschakelen < uitschakelen, binnen 20–75 °C.";
 $("return-gate-return").textContent=fixed(returnSettings.returnStart)+" °C";
 $("return-gate-supply").textContent=fixed(returnSettings.supplyStart)+" °C";
 $("return-gate-slider").value=returnSettings.returnStart;
 $("return-gate-supply-slider").value=returnSettings.supplyStart;
 $("return-gate-valid").checked=returnSettings.valid;
 $("return-gate-enabled").checked=returnSettings.enabled;
 const target=roomSettings.target??s.target;
 const sample=parts({...s,target,room:roomSettings.start??s.room}).limited;
 $("return-gate-target").textContent=fixed(sample)+" °C";
 $("return-gate-warning").textContent=returnSettings.enabled&&returnSettings.stopAt>=sample
  ?"De bovengrens ligt boven of gelijk aan de gevraagde aanvoertemperatuur. De retour bereikt die grens mogelijk nooit; de ketel kan de brander intussen zelf stoppen."
  :"De Vaillant bepaalt zelf het branderbedrijf. Een uitgestelde cv-vrijgave is niet hetzelfde als langere gemeten brandercycli; vooral de retour bij werkelijke circulatie is relevant.";
}
function initPump() {
 const changed=()=>{
  updatePumpWarning();
  if(view==="sim")run(Number($("sim-cursor").value));
 };
 // The prominent button toggles continuous circulation + 45-minute postrun.
 // OFF means circulation only during room demand. The select remains
 // available to compare a boiler-like "CH permission only" scenario.
 $("sim-pump-toggle").addEventListener("click",()=>{
  pumpSettings.mode=pumpSettings.mode==="room-postrun"?"room":"room-postrun";
  $("sim-pump-mode").value=pumpSettings.mode;
  changed();
 });
 $("sim-pump-mode").addEventListener("change",event=>{
  pumpSettings.mode=event.target.value;
  changed();
 });
 $("sim-pump-mode").value=pumpSettings.mode;
 updatePumpWarning();
}
function updatePumpWarning(){
 const active=pumpSettings.mode==="room-postrun";
 const button=$("sim-pump-toggle");
 button.textContent="Continue pomp + 45 min naloop: "+(active?"AAN":"UIT");
 button.setAttribute("aria-pressed",String(active));
 button.classList.toggle("active",active);
 const risky=pumpSettings.mode==="release"&&returnSettings.enabled;
 $("sim-pump-warning").textContent=risky
  ?"Let op: met pomp uitsluitend bij cv-vrijgave kan de retour tijdens de wachttijd niet betrouwbaar worden gemeten. De simulatie blokkeert daarom een terugkeer naar cv-vrijgave zolang er geen circulatie is. Deze combinatie is geen bruikbare live regelstrategie."
  :pumpSettings.mode==="room-postrun"
   ?"Fictieve pomp volgt kamervraag en loopt na het einde nog 45 minuten door. Dit stelt niet vast welke d.1/d.18-modus op de echte ketel actief is."
   :"Fictieve pomp draait bij kamervraag, ook wanneer de retourhysterese de cv-vrijgave blokkeert. Echte pompwerking is nog niet gemeten.";
}
function initReturnGate() {
 const changed=()=>{updateReturnGate(readState());updatePumpWarning();if(view==="sim")run(Number($("sim-cursor").value));};
 for(const [id,key] of [["return-gate-on","startAt"],["return-gate-off","stopAt"]]){
  $(id).addEventListener("input",e=>{
   returnSettings[key]=e.target.value===""?NaN:Number(e.target.value);
   changed();
  });
 }
 $("return-gate-enabled").addEventListener("change",e=>{returnSettings.enabled=e.target.checked;changed();});
 $("return-gate-valid").addEventListener("change",e=>{returnSettings.valid=e.target.checked;changed();});
 $("return-gate-slider").addEventListener("input",e=>{returnSettings.returnStart=Number(e.target.value);changed();});
 $("return-gate-supply-slider").addEventListener("input",e=>{returnSettings.supplyStart=Number(e.target.value);changed();});
 $("return-gate-reset").addEventListener("click",()=>{
  Object.assign(returnSettings,{enabled:false,returnStart:35,supplyStart:45,startAt:30,stopAt:42,valid:true});
  $("return-gate-on").value=30;$("return-gate-off").value=42;
  changed();
 });
}

let readState,changeOutdoor,logEvent,view="static",points=[],timer=null;
function stop(){if(timer!==null){clearInterval(timer);timer=null;}$("sim-play").textContent="Afspelen";}
function step(index){
 const n=clamp(Number(index)||0,0,points.length-1),p=points[n];
 $("sim-cursor").value=n;$("sim-step").textContent=fixed(p.h)+" uur";
 $("sim-room").textContent=fixed(p.room)+" °C";
 $("sim-outdoor").textContent=fixed(p.outdoor)+" °C";
 $("sim-flow").textContent=p.flow===null?"—":fixed(p.flow)+" °C";
 $("sim-measured-flow").textContent=Number.isFinite(p.measuredFlow)?fixed(p.measuredFlow)+" °C":"—";
 $("sim-measured-return").textContent=Number.isFinite(p.measuredReturn)?fixed(p.measuredReturn)+" °C":"—";
 $("sim-water-delta").textContent=Number.isFinite(p.measuredReturn)&&Number.isFinite(p.measuredFlow)?fixed(Math.max(0,p.measuredFlow-p.measuredReturn))+" °C":"—";
 $("sim-room-demand").textContent=p.roomDemand?"Ja":"Nee";
 $("sim-demand").textContent=p.demand?"Ja":"Nee";
 $("sim-pump").textContent=p.pumpOn?"Aan":"Uit";
 $("sim-return-quality").textContent=!Number.isFinite(p.measuredReturn)
  ?"Geen geldige meting":p.pumpOn
  ?"Circulerende retour":"Lokale ketelretour (pomp uit)";
 $("sim-integral").textContent=fixed(p.integral)+" °C";
 const lower=fixed(p.target-roomSettings.hysteresis),upper=fixed(p.target+roomSettings.hysteresis);
 const config=returnSettings.enabled
  ?" Retourgrenzen: inschakelen ≤ "+fixed(returnSettings.startAt)+" °C, uitschakelen ≥ "+fixed(returnSettings.stopAt)+" °C."
  :" Extra retourhysterese uit.";
 $("sim-status").textContent=(!p.valid||readState().mode!=="heat")
  ?p.reason+"; virtuele cv-vrijgave uit."
  :("Kamer "+p.room.toFixed(3).replace(".",",")+" °C; kamerhysterese "+lower+"–"+upper+
   " °C. "+(p.demand?"CV-vrijgave AAN. ":"CV-vrijgave UIT. ")+
   (p.pumpOn?"Pomp draait (fictief). ":"Pomp uit (fictief). ")+p.gateReason+"."+config);
 $("return-gate-room").textContent=p.roomDemand?"Ja":"Nee";
 $("return-gate-state").textContent=p.demand?"CV-VRIJGAVE AAN (DEMO)":"CV-VRIJGAVE UIT (DEMO)";
 $("return-gate-reason").textContent=p.gateReason;
 const final=points[points.length-1];
 const time=points.slice(0,-1).filter(x=>x.demand).length*5;
 const pumpMinutes=points.slice(0,-1).filter(x=>x.pumpOn).length*5;
 const residualMinutes=points.slice(0,-1).filter(x=>x.pumpOn&&!x.demand).length*5;
 $("sim-cycle-summary").textContent="Simulatie over "+$("sim-duration").value+
  " uur: "+final.starts+" × cv-vrijgave aan, "+final.stops+
  " × cv-vrijgave uit; "+time+" minuten cv-vrijgave, "+pumpMinutes+
  " minuten pomp AAN ("+residualMinutes+
  " minuten zonder cv-vrijgave). Dit zijn geen gemeten pomp-/branderminuten.";
 timeline($("sim-chart"),points,n,Number($("sim-duration").value));
}
function run(cursor=0){
 stop();const scenario=$("sim-scenario").value,hours=Number($("sim-duration").value);
 points=simulate(readState(),scenario,hours,returnSettings,roomSettings,pumpSettings);
 $("sim-cursor").max=points.length-1;
 $("sim-info").textContent="Scenario: "+$("sim-scenario").selectedOptions[0].text+
  " — fictief water-/woningmodel, stappen van 5 minuten. Pas de hysterese aan en bekijk het verschil op dezelfde grafiek.";
 step(cursor);
}
function render(s){
 compare($("curve-chart"),s);const p=parts(s);
 $("curve-base-comp").textContent=fixed(p.base)+" °C";
 $("curve-room-comp").textContent=(p.correction>=0?"+":"")+fixed(p.correction)+" °C";
 $("curve-raw-comp").textContent=fixed(p.raw)+" °C";
 $("curve-bound-comp").textContent=fixed(p.limited)+" °C";
 $("curve-limit").textContent=p.raw<p.limited?"Minimumgrens actief":p.raw>p.limited?"Maximumgrens actief":"Geen begrenzing actief";
 updateReturnGate(s);
 if(view==="sim")run(Number($("sim-cursor").value));
}
function init(helpers){
 readState=helpers.getState;changeOutdoor=helpers.setOutdoor;logEvent=helpers.record;
 initRoomInputs();
 initReturnGate();
 initPump();
 document.querySelectorAll("[data-curve-view]").forEach(button=>button.addEventListener("click",()=>{
  view=button.dataset.curveView;stop();
  for(const b of document.querySelectorAll("[data-curve-view]")){const selected=b.dataset.curveView===view;b.classList.toggle("active",selected);b.setAttribute("aria-pressed",String(selected));}
  $("curve-panel-static").hidden=view!=="static";$("curve-panel-sim").hidden=view!=="sim";
  if(view==="sim")run();
 }));
 $("sim-run").addEventListener("click",()=>{run();logEvent("Stooklijn","Simulatie herberekend (demo)");});
 $("sim-scenario").addEventListener("change",()=>{
  // Never overwrite a manually set start temperature on scenario changes.
  if(!roomSettings.customStart){
   roomSettings.start=defaultRoomStart(readState(),$("sim-scenario").value,roomSettings.target);
   $("sim-room-start").value=roomSettings.start.toFixed(1);
  }
  run();
 });
 $("sim-duration").addEventListener("change",()=>run());
 $("sim-cursor").addEventListener("input",e=>{stop();step(e.target.value);});
 $("sim-play").addEventListener("click",()=>{
  if(timer!==null){stop();return;}
  if(!points.length)run();
  if(Number($("sim-cursor").value)>=points.length-1)step(0);
  $("sim-play").textContent="Pauzeren";
  timer=setInterval(()=>{const next=Number($("sim-cursor").value)+1;if(next>=points.length)stop();else step(next);},110);
 });
 const svg=$("curve-chart");
 function move(e){
  const r=svg.getBoundingClientRect();if(!r.width)return;
  const vx=(e.clientX-r.left)/r.width*740;
  const temp=Math.round(clamp(-20+(vx-56)/630*50,-20,30)*2)/2;
  changeOutdoor(temp);
 }
 svg.addEventListener("pointerdown",move);
 svg.addEventListener("pointermove",e=>{if(e.buttons&1)move(e);});
 svg.tabIndex=0;
 svg.addEventListener("keydown",e=>{if(e.key==="ArrowLeft"||e.key==="ArrowRight"){e.preventDefault();changeOutdoor(clamp(readState().outdoor+(e.key==="ArrowLeft"?-0.5:0.5),-20,30));}});
}
// Pure chart renderers are exported for regression tests of actual SVG paths.
const api={parts,controller,simulate,render,init,stop,compare,timeline,returnGate};
root.VaillantCurveDemo=api;
if(typeof module!=="undefined"&&module.exports)module.exports=api;
})(typeof window==="undefined"?globalThis:window);
