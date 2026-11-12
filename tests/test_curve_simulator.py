"""Browser/offline curve model contract: parity with Python and fail-closed sensors."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import shutil
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "addons" / "vaillant-ebus-control" / "app"
sys.path.insert(0, str(APP))
from vaillant_control.algorithm import Curve, Reading, Thermostat

SCRIPT = ROOT / "addons" / "vaillant-ebus-control" / "webui" / "curve_simulator.js"

@pytest.mark.skipif(not shutil.which("node"), reason="Node not installed")
def test_browser_pi_matches_controller():
    code = """
const m=require(process.argv[1]);
const s={mode:"heat",target:21,slope:1.2,kp:2,ki:0.005,flowMin:30,flowMax:65};
const run=m.controller(s);
const frames=[
[0,18,true],[300,18.5,true],[600,20.9,true],[900,21.25,true],
[1200,18.5,false],[1500,18.5,true]];
console.log(JSON.stringify(frames.map(([time,room,valid])=>run({time,room,outdoor:5,valid}))));
"""
    output=subprocess.check_output(["node","-e",code,str(SCRIPT)],text=True)
    browser=json.loads(output)
    py=Thermostat(Curve(slope=1.2,kp=2,ki=0.005,min_flow=30,max_flow=65))
    zero=datetime(2026,10,30,tzinfo=timezone.utc)
    for index, (room, valid) in enumerate([(18,True),(18.5,True),(20.9,True),(21.25,True),(18.5,False),(18.5,True)]):
        now=zero+timedelta(seconds=300*index)
        result=py.evaluate(mode="heat",target=21,room=Reading(room,now,"test"),
            outdoor=Reading(5,now,"test") if valid else None,now=now)
        assert browser[index]["demand"]==result.demand
        assert browser[index]["flow"]==result.requested_flow_c
        assert browser[index]["integral"]==pytest.approx(py.integral)

@pytest.mark.skipif(not shutil.which("node"), reason="Node not installed")
def test_scenarios_bounded_and_fail_closed():
    code = """
const m=require(process.argv[1]);
const s={mode:"heat",target:21,room:18,outdoor:5,roomValid:true,outdoorValid:true,
slope:1.2,kp:2,ki:0.005,flowMin:30,flowMax:65};
console.log(JSON.stringify(Object.fromEntries(["cold","sunny","target","fault"].map(x=>[x,m.simulate(s,x,6)]))));
"""
    output=subprocess.check_output(["node","-e",code,str(SCRIPT)],text=True)
    scenarios=json.loads(output)
    for name,frames in scenarios.items():
        assert len(frames)==73,name
        assert all(f["flow"] is None or 30<=f["flow"]<=65 for f in frames)
        assert all(-5<=f["integral"]<=5 for f in frames)
    assert any(f["demand"] for f in scenarios["fault"][:24])
    assert all(f["flow"] is None and not f["demand"] and f["integral"]==0
               for f in scenarios["fault"][24:])


@pytest.mark.skipif(not shutil.which("node"), reason="Node not installed")
def test_svg_charts_have_real_coordinate_paths():
    """Prevent invisible graphs caused by rejecting [x,y] arrays as nonfinite scalars."""
    code = r"""
const assert = require("node:assert/strict");
const m = require(process.argv[1]);
const state = { mode:"heat", target:21.5, room:18.2, outdoor:6,
  roomValid:true, outdoorValid:true, slope:1.2, kp:2, ki:0.005,
  flowMin:30, flowMax:65 };
const curve = {innerHTML:""};
m.compare(curve, state);
const mainPaths = [...curve.innerHTML.matchAll(/<path class="curve-(?:base|room|bound)-line" d="([^"]*)"/g)];
assert.equal(mainPaths.length, 3, "Expected 3 comparison curves");
for (const [, d] of mainPaths) {
  assert.ok(d.startsWith("M"), "SVG curve path must start with a move command");
  assert.ok((d.match(/[ML]/g) || []).length >= 100, "Curve must contain plotted points");
  assert.ok(!/NaN|Infinity/.test(d));
}
const frames = m.simulate(state, "cold", 6);
const timeline = {innerHTML:""};
m.timeline(timeline, frames, 0, 6);
const timePaths = [...timeline.innerHTML.matchAll(/<path class="curve-(?:base|room|bound)-line" d="([^"]*)"/g)];
assert.equal(timePaths.length, 3, "Expected target/room/flow traces");
for (const [, d] of timePaths) {
  assert.ok(d.startsWith("M"), "Timeline trace must not be blank");
  assert.ok((d.match(/[ML]/g) || []).length >= 10, "Timeline must have multiple samples");
  assert.ok(!/NaN|Infinity/.test(d));
}
console.log(JSON.stringify({curves: mainPaths.length, timeline: timePaths.length,
  comparison_points: (mainPaths[0][1].match(/[ML]/g)||[]).length}));
"""
    output = subprocess.check_output(["node", "-e", code, str(SCRIPT)], text=True, timeout=15)
    result = json.loads(output)
    assert result == {"curves": 3, "timeline": 3, "comparison_points": 101}


@pytest.mark.skipif(not shutil.which("node"), reason="Node not installed")
def test_timeline_separates_room_and_supply_scales():
    """Room and flow paths must occupy different vertical panels with their own axes."""
    code = r"""
const assert = require("node:assert/strict");
const demo = require(process.argv[1]);
const state = { mode:"heat", target:21.5, room:18.2, outdoor:6,
 roomValid:true, outdoorValid:true, slope:1.2, kp:2, ki:0, flowMin:30, flowMax:65 };
const frames = demo.simulate(state, "sunny", 6);
const svg = {innerHTML:""};
demo.timeline(svg, frames, 37, 6);
assert.ok(svg.innerHTML.includes("KAMER / DOEL"));
assert.ok(svg.innerHTML.includes("AANVOER EN RETOUR: FICTIEF"));
assert.ok(svg.innerHTML.includes('class="sim-demand-band"'), "Demand-on strip must be drawn");
assert.ok(svg.innerHTML.includes('class="sim-room-cursor"'));
assert.ok(svg.innerHTML.includes('class="sim-flow-cursor"'));
function yValues(className) {
 const match = svg.innerHTML.match(new RegExp('<path class="'+className+'" d="([^"]*)"'));
 assert.ok(match && match[1], "Missing graph path for "+className);
 const points = [...match[1].matchAll(/[ML](-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/g)];
 assert.ok(points.length>=20, "Not enough coordinates for "+className);
 return points.map(match => Number(match[2]));
}
for(const name of ["curve-base-line","curve-room-line"]) {
 assert.ok(yValues(name).every(y=>y>=40&&y<=151), "Room graph escaped upper scale");
}
assert.ok(yValues("curve-bound-line").every(y=>y>=204&&y<=304), "Flow escaped lower scale");
assert.ok(!/NaN|Infinity/.test(svg.innerHTML));
console.log("separate scales passed");
"""
    output = subprocess.check_output(["node", "-e", code, str(SCRIPT)], text=True, timeout=15)
    assert "separate scales passed" in output


@pytest.mark.skipif(not shutil.which("node"), reason="Node not installed")
def test_hysteresis_can_request_heat_above_rounded_target():
    code = r"""
const assert = require("node:assert/strict");
const demo = require(process.argv[1]);
const controller = demo.controller({mode:"heat",target:21.5,slope:1.2,
 kp:2,ki:0,flowMin:30,flowMax:65});
assert.equal(controller({time:0,room:21.2,outdoor:9}).demand,true);
assert.equal(controller({time:300,room:21.695,outdoor:9}).demand,true);
assert.equal(controller({time:600,room:21.7,outdoor:9}).demand,false);
console.log("hysteresis passed");
"""
    assert "hysteresis passed" in subprocess.check_output(
        ["node", "-e", code, str(SCRIPT)], text=True, timeout=15)


def test_svg_annotation_css_blocks_inherited_icon_stroke():
    """Regression: global svg stroke must not outline SVG text or activity tracks."""
    css = (ROOT / "addons/vaillant-ebus-control/webui/styles.css").read_text(encoding="utf8")
    source = SCRIPT.read_text(encoding="utf8")
    import re
    assert re.search(r"#sim-chart\s+text\s*\{[^}]*stroke\s*:\s*none\s*;", css), (
        "Chart text must explicitly override inherited svg stroke")
    assert re.search(r"#sim-chart\s+\.sim-axis-title\s*\{[^}]*stroke\s*:\s*none\s*;", css), (
        "Axis headings must not inherit global svg icon stroke")
    assert re.search(r"#sim-chart\s+\.sim-demand-band\s*\{[^}]*stroke\s*:\s*none\s*;", css), (
        "Demand activity should not have icon-style borders")
    assert re.search(r"#sim-chart\s+\.sim-demand-track\s*\{[^}]*stroke\s*:\s*none\s*;", css)
    assert 'class="sim-demand-track"' in source


@pytest.mark.skipif(not shutil.which("node"), reason="Node not installed")
def test_virtual_flow_gate_hysteresis_and_failsafe():
    """The return gate is CV permission only, never a command to ignite a burner."""
    code = r"""
const assert=require('node:assert/strict'),m=require(process.argv[1]);
const gate=m.returnGate;
const base={roomDemand:true,sensorValid:true,startAt:30,stopAt:42};
const check=(previous,temp,overrides={})=>gate(previous,{...base,measuredReturn:temp,...overrides}).allowed;
assert.equal(check(false,35),false,'between thresholds must not start');
assert.equal(check(false,30),true,'start at lower boundary');
assert.equal(check(true,35),true,'hold previous permission between limits');
assert.equal(check(true,42),false,'stop at upper boundary');
assert.equal(check(true,30,{roomDemand:false}),false,'room satisfied always vetoes flow');
assert.equal(check(true,30,{sensorValid:false}),false,'bad sensor fails closed');
assert.equal(check(true,NaN),false,'NaN fails closed');
assert.equal(check(true,30,{startAt:55,stopAt:40}),false,'invalid band fails closed');
console.log('flow gate passed');
"""
    output=subprocess.check_output(["node","-e",code,str(SCRIPT)],text=True,timeout=15)
    assert "flow gate passed" in output


@pytest.mark.skipif(not shutil.which("node"), reason="Node not installed")
def test_flow_gate_changes_full_graph_temperature_and_permission_history():
    """Changing thresholds must affect the 6h replay itself, not a separate yes/no widget."""
    code = r"""
const assert=require("node:assert/strict");
const m=require(process.argv[1]);
const s={mode:"heat",target:21.5,room:18.2,outdoor:6,roomValid:true,outdoorValid:true,
 slope:1.2,kp:2,ki:0.005,flowMin:30,flowMax:65};
const gate={enabled:true,startAt:30,stopAt:42,returnStart:35,supplyStart:45,valid:true};
const normal=m.simulate(s,"cold",6,{...gate,enabled:false});
const coupled=m.simulate(s,"cold",6,gate);
assert.equal(normal.length,73);
assert.equal(coupled.length,73);
assert.ok(coupled.some(x=>x.roomDemand&&!x.demand), "flow band must block otherwise-valid room demand");
assert.ok(coupled.some(x=>x.roomDemand&&x.demand), "flow band must allow CH at the lower boundary");
assert.ok(coupled.some(x=>x.starts>0), "replay must start virtual CH at lower return boundary");
assert.ok(coupled.every(x=>!x.demand||x.roomDemand), "room thermostat always vetoes CH");
assert.ok(coupled.some((x,i)=>Math.abs(x.measuredFlow-normal[i].measuredFlow)>0.01),
 "changing flow hysteresis must change measured supply history");
assert.ok(coupled.some((x,i)=>Math.abs(x.room-normal[i].room)>0.01),
 "changing flow hysteresis must change room temperature history");
for(const p of coupled){
 assert.ok(p.measuredFlow>=0&&p.measuredFlow<=85);
 assert.ok(p.flow===null||(p.flow>=30&&p.flow<=65));
}
const chart={innerHTML:""};
m.timeline(chart,coupled,35,6);
for(const name of ["sim-measured-line","sim-return-line","curve-bound-line","sim-room-demand-band","sim-demand-band"]){
 assert.ok(chart.innerHTML.includes('class="'+name+'"'),"plot must include "+name);
}
const measured=chart.innerHTML.match(/<path class="sim-measured-line" d="([^"]*)"/);
const returned=chart.innerHTML.match(/<path class="sim-return-line" d="([^"]*)"/);
assert.ok(returned&&returned[1].startsWith("M"));
assert.ok(measured&&measured[1].startsWith("M"));
assert.ok((measured[1].match(/[ML]/g)||[]).length>=70);
console.log(JSON.stringify({starts:coupled.at(-1).starts,stops:coupled.at(-1).stops,
 difference:Math.abs(coupled[50].room-normal[50].room)}));
"""
    output=subprocess.check_output(["node","-e",code,str(SCRIPT)],text=True,timeout=15)
    result=json.loads(output)
    assert result["starts"]>0
    assert result["difference"]>0.01


@pytest.mark.skipif(not shutil.which("node"), reason="Node not installed")
def test_flow_sensor_failure_disables_cv_permission_during_replay():
    code = r"""
const assert=require("node:assert/strict");
const m=require(process.argv[1]);
const s={mode:"heat",target:21.5,room:18.2,outdoor:6,roomValid:true,outdoorValid:true,
 slope:1.2,kp:2,ki:0.005,flowMin:30,flowMax:65};
const failed=m.simulate(s,"cold",6,{enabled:true,startAt:30,stopAt:42,returnStart:35,supplyStart:45,valid:false});
assert.ok(failed.every(p=>!p.demand));
assert.ok(failed.every(p=>p.measuredReturn===null));
const badBounds=m.simulate(s,"cold",6,{enabled:true,startAt:55,stopAt:40,returnStart:35,supplyStart:45,valid:true});
assert.ok(badBounds.every(p=>!p.demand));
const lostOutdoor=m.simulate(s,"fault",6,{enabled:true,startAt:30,stopAt:42,returnStart:28,supplyStart:45,valid:true});
assert.ok(lostOutdoor.slice(24).every(p=>!p.demand&&!p.roomDemand));
console.log("fail-closed replay passed");
"""
    assert "fail-closed replay passed" in subprocess.check_output(
        ["node","-e",code,str(SCRIPT)],text=True,timeout=15)


@pytest.mark.skipif(not shutil.which("node"), reason="Node not installed")
def test_user_room_start_and_target_change_simulated_temperature_curves():
    code = r"""
const assert=require("node:assert/strict");
const m=require(process.argv[1]);
const s={mode:"heat",target:21.5,room:18.2,outdoor:6,roomValid:true,outdoorValid:true,
 slope:1.2,kp:2,ki:0.005,flowMin:30,flowMax:65};
const gate={enabled:false,returnStart:30,supplyStart:40,valid:true};
for(const scenario of ["cold","sunny","target","fault"]) {
 const opts={start:23.4,target:20.5,hysteresis:0.3};
 const output=m.simulate(s,scenario,6,gate,opts);
 assert.equal(output.length,73);
 assert.equal(output[0].room,23.4,"manual starting temperature must override any scenario default");
 assert.equal(output[0].target,20.5,"manual target must override HA demo state");
}
const cold=m.simulate(s,"cold",6,gate,{start:16,target:21.5,hysteresis:0.2});
const warm=m.simulate(s,"cold",6,gate,{start:22,target:21.5,hysteresis:0.2});
assert.equal(cold[0].room,16);
assert.equal(warm[0].room,22);
assert.ok(cold.some((p,i)=>Math.abs(p.room-warm[i].room)>0.5),"full room history must change");
assert.ok(cold.some((p,i)=>p.demand!==warm[i].demand),"room heat decisions must change");
const lowerTarget=m.simulate(s,"cold",6,gate,{start:20,target:19,hysteresis:0.2});
const higherTarget=m.simulate(s,"cold",6,gate,{start:20,target:23,hysteresis:0.2});
assert.ok(lowerTarget.every(p=>p.target===19));
assert.ok(higherTarget.every(p=>p.target===23));
assert.ok(lowerTarget.some((p,i)=>p.roomDemand!==higherTarget[i].roomDemand));
const a={innerHTML:""},b={innerHTML:""};
m.timeline(a,cold,14,6);m.timeline(b,warm,14,6);
const find=svg=>svg.innerHTML.match(/<path class="curve-room-line" d="([^"]*)"/)[1];
assert.notEqual(find(a),find(b),"the rendered graph itself must be different");
console.log("room temperature controls passed");
"""
    assert "room temperature controls passed" in subprocess.check_output(
        ["node", "-e", code, str(SCRIPT)], text=True, timeout=15)


@pytest.mark.skipif(not shutil.which("node"), reason="Node not installed")
def test_custom_room_hysteresis_changes_demand_without_changing_safety():
    code = r"""
const assert=require("node:assert/strict");
const m=require(process.argv[1]);
const s={mode:"heat",target:21.5,room:18.2,outdoor:6,roomValid:true,outdoorValid:true,
 slope:1.2,kp:2,ki:0.005,flowMin:30,flowMax:65};
const gate={enabled:false,measured:40,valid:true};
const close=m.simulate(s,"cold",6,gate,{start:21.0,target:21.5,hysteresis:0.2});
const wide=m.simulate(s,"cold",6,gate,{start:21.0,target:21.5,hysteresis:0.8});
assert.equal(close[0].roomDemand,true,"0.2°C hysteresis should start with a 0.5°C deficit");
assert.equal(wide[0].roomDemand,false,"0.8°C hysteresis should wait at same deficit");
const invalid={...s,outdoorValid:false};
const fail=m.simulate(invalid,"cold",6,gate,{start:15,target:25,hysteresis:0.2});
assert.ok(fail.every(p=>!p.demand),"room controls must not bypass invalid sensors");
console.log("hysteresis adjustment passed");
"""
    assert "hysteresis adjustment passed" in subprocess.check_output(
        ["node", "-e", code, str(SCRIPT)], text=True, timeout=15)


@pytest.mark.skipif(not shutil.which("node"), reason="Node not installed")
def test_return_temperature_gates_cv_only_when_cold_enough():
    code=r"""
const assert=require("node:assert/strict");
const m=require(process.argv[1]);
const gate={enabled:true,startAt:30,stopAt:42,returnStart:35,supplyStart:45,valid:true};
const s={mode:"heat",target:21.5,room:19.5,outdoor:0,roomValid:true,outdoorValid:true,
  slope:1.2,kp:2,ki:0,flowMin:30,flowMax:65};
const frames=m.simulate(s,"cold",6,gate,{start:19,target:21.5,hysteresis:0.2});
assert.equal(frames[0].measuredFlow,45,"supply begins independently");
assert.equal(frames[0].measuredReturn,35,"return begins independently");
assert.equal(frames[0].roomDemand,true);
assert.equal(frames[0].demand,false,"warm return must prevent starting");
assert.ok(frames.some(p=>p.demand&&p.measuredReturn<=30),"restarts only at cold return");
assert.ok(frames.some(p=>p.measuredFlow>p.measuredReturn),"return must be plotted below supply");
assert.ok(frames.every(p=>p.measuredReturn===null||p.measuredFlow>=p.measuredReturn),"synthetic return should not exceed supply");
assert.ok(frames.every(p=>!p.demand||p.roomDemand),"room veto stays authoritative");
const svg={innerHTML:""};
m.timeline(svg,frames,12,6);
const path=svg.innerHTML.match(/<path class="sim-return-line" d="([^"]*)"/);
assert.ok(path&&path[1]&&path[1].startsWith("M"));
assert.ok((path[1].match(/[ML]/g)||[]).length>50);
console.log("return behavior verified");
"""
    assert "return behavior verified" in subprocess.check_output(
       ["node","-e",code,str(SCRIPT)],text=True,timeout=15)


@pytest.mark.skipif(not shutil.which("node"), reason="Node not installed")
def test_pump_circulates_while_return_gate_blocks_ch():
    """Room demand should be able to circulate residual heat without CH permission."""
    code = r"""
const assert=require("node:assert/strict"),m=require(process.argv[1]);
const s={mode:"heat",target:21.5,room:19,outdoor:0,roomValid:true,outdoorValid:true,
 slope:1.2,kp:2,ki:0,flowMin:30,flowMax:65};
const gate={enabled:true,startAt:30,stopAt:42,returnStart:35,supplyStart:45,valid:true};
const room={start:19,target:21.5,hysteresis:0.2};
const pumped=m.simulate(s,"cold",6,gate,room,{mode:"room"});
const limited=m.simulate(s,"cold",6,gate,room,{mode:"release"});
assert.equal(pumped.length,73);
assert.ok(pumped[0].pumpOn,"pump should circulate under room demand");
assert.equal(pumped[0].demand,false,"hot return should prevent CH permission");
assert.ok(pumped.some(p=>p.pumpOn&&!p.demand),"pump must run while CV permission is blocked");
assert.ok(pumped.some(p=>p.demand),"cooling return should eventually release CH");
assert.ok(pumped.some(p=>p.pumpOn&&!p.demand&&p.measuredReturn!==null));
assert.ok(pumped.some(p=>p.demand&&p.measuredReturn!==null&&p.measuredReturn<=gate.startAt),
 "CV permission must restart only once measured circulating return is cold enough");
assert.equal(limited[0].pumpOn,false,"release-only mode should begin without circulation");
assert.ok(limited.every(p=>!p.demand),"cannot restart via an untrusted stagnant return probe");
assert.ok(limited.every(p=>Number.isFinite(p.measuredReturn)),"local return probe remains visible without circulation");
assert.ok(limited.every(p=>!p.returnSensorValid),"local return is not trusted as circulating system return");
assert.ok(limited.at(-1).measuredFlow>pumped.at(-1).room,
 "fictional supply remains above room while pump model runs");
const svg={innerHTML:""};
m.timeline(svg,pumped,20,6);
assert.ok(svg.innerHTML.includes('class="sim-pump-band"'));
assert.ok(svg.innerHTML.includes('class="sim-pump-track"'));
console.log("circulation decoupled");
"""
    assert "circulation decoupled" in subprocess.check_output(
        ["node","-e",code,str(SCRIPT)],text=True,timeout=15)


@pytest.mark.skipif(not shutil.which("node"), reason="Node not installed")
def test_pump_follows_room_demand_and_postrun_policy():
    """Circulation can outlast room demand for 45 minutes in the demo."""
    code = r"""
const assert=require("node:assert/strict"),m=require(process.argv[1]);
const s={mode:"heat",target:21.5,room:21,outdoor:6,roomValid:true,outdoorValid:true,
 slope:1.2,kp:2,ki:0,flowMin:30,flowMax:65};
const room={start:21,target:21.5,hysteresis:0.2};
const gate={enabled:false,startAt:30,stopAt:42,returnStart:30,supplyStart:50,valid:true};
const immediate=m.simulate(s,"sunny",24,gate,room,{mode:"room"});
const postrun=m.simulate(s,"sunny",24,gate,room,{mode:"room-postrun"});
assert.equal(postrun.length,289);
assert.ok(postrun.every(p=>p.pumpOn===p.roomDemand || (p.pumpOn&&!p.roomDemand)),
 "postrun must never disable pump during room demand");
assert.ok(immediate.every(p=>p.pumpOn===p.roomDemand),
 "room mode means pump matches room demand");
assert.ok(postrun.some(p=>p.pumpOn&&!p.roomDemand),
 "45-min postrun must keep circulation on after heat demand ends");
assert.ok(postrun.some(p=>!p.roomDemand&&!p.pumpOn),
 "postrun should eventually expire");
assert.ok(postrun.every(p=>!p.demand||p.roomDemand),"room veto must remain authoritative");
console.log("postrun works");
"""
    assert "postrun works" in subprocess.check_output(
        ["node","-e",code,str(SCRIPT)],text=True,timeout=15)


@pytest.mark.skipif(not shutil.which("node"), reason="Node not installed")
def test_pump_compare_modes_and_stagnant_return_path():
    """Pump toggle modes must change the time series, never erase local return readings."""
    code = r"""
const assert=require("node:assert/strict");
const m=require(process.argv[1]);
const s={mode:"heat",target:21.5,room:19,outdoor:0,roomValid:true,outdoorValid:true,
 slope:1.2,kp:2,ki:0,flowMin:30,flowMax:65};
const g={enabled:true,startAt:30,stopAt:42,returnStart:35,supplyStart:45,valid:true};
const room={start:19,target:21.5,hysteresis:0.2};
const on=m.simulate(s,"cold",24,g,room,{mode:"room-postrun"});
const off=m.simulate(s,"cold",24,g,room,{mode:"room"});
const stopped=m.simulate(s,"cold",6,g,room,{mode:"release"});
assert.equal(on.length,289);
assert.equal(off.length,289);
assert.ok(on.every((p,i)=>!off[i].pumpOn||p.pumpOn),
 "45-minute postrun cannot have fewer pump-on steps than immediate off");
assert.ok(on.some((p,i)=>p.pumpOn&&!off[i].pumpOn),
 "postrun should add pump-on time when room heat demand ends");
assert.ok(stopped.every(p=>!p.pumpOn));
assert.ok(stopped.every(p=>Number.isFinite(p.measuredReturn)),
 "the local ReturnTemp reading must still exist when the pump is stopped");
assert.ok(stopped.every(p=>!p.returnSensorValid),
 "stagnant ReturnTemp is not suitable for CH gate decisions");
assert.ok(stopped.every(p=>!p.demand),
 "return gate with no circulation must fail closed");
const graph={innerHTML:""};
m.timeline(graph,stopped,15,6);
const dashed=graph.innerHTML.match(/<path class="sim-return-stagnant-line" d="([^"]*)"/);
assert.ok(dashed && dashed[1].startsWith("M"),
 "non-circulating return should be drawn as a dashed graph path");
assert.ok((dashed[1].match(/[ML]/g)||[]).length >= 100,
 "retour curve must be continuously visible when the pump is off");
const flowing={innerHTML:""};
m.timeline(flowing,on,20,24);
const solid=flowing.innerHTML.match(/<path class="sim-return-line" d="([^"]*)"/);
assert.ok(solid && solid[1].startsWith("M"),
 "return should be solid whenever water is circulating");
console.log("pump switch and return path verified");
"""
    output=subprocess.check_output(["node","-e",code,str(SCRIPT)],text=True,timeout=15)
    assert "pump switch and return path verified" in output
