#!/usr/bin/env python3
"""SERVIDOR TX780: correct F10 UI and expose real V95 launch failures.

Only touches the exact owner-pinned disposable source checkout after TX775.
Do not alter signed neural weights, worker SHA, game journal or model quality.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess

EXPECTED_SHA="aeb9ff9326e418fbabe2d53dff7891f4fb340c37"
TEMPLATE=Path("reference/tx331-clean-product-host/rpg_live_plugin/versions/tx757-patched-template.js")

OLD_SPAWN='''                    if(child&&child.on)child.on("error",function(){
                        workerBusy=false;
                        setV95PanelState("V95 local: fallo al iniciar motor");
                    });
                    setV95PanelState("Iniciando V95 local (sin Internet)");
                    workerBusy=false;'''
NEW_SPAWN='''                    // TX780: an installed V95 can exit before publishing
                    // the local descriptor. Record SAFE error categories.
                    if(child&&child.on){
                        child.on("error",function(error){
                            workerBusy=false;
                            var code=String(error&&error.code||"ERROR");
                            if(!/^(ENOENT|EACCES|EPERM|EBUSY|EINVAL)$/.test(code))
                                code="ERROR";
                            setV95PanelState("IA: fallo de arranque ("+code+")");
                            cacheDiagnostic("worker_spawn_failed",{code:code});
                        });
                        child.on("exit",function(code){
                            workerBusy=false;
                            if(!descriptor()){
                                var safeExit=Number.isInteger(code)&&code>=0&&
                                    code<=65535?code:-1;
                                setV95PanelState("IA: motor se cerró ("+safeExit+")");
                                cacheDiagnostic("worker_exited_before_bridge",{
                                    exit_code:safeExit
                                });
                            }
                        });
                    }
                    setV95PanelState("IA: iniciando motor local");
                    // Absence of an authenticated bridge is not readiness.
                    setTimeout(function(){
                        if(child && typeof child.pid==="number" &&
                           child.pid>0 && !descriptor()){
                            setV95PanelState("IA: sin puente local");
                            cacheDiagnostic("worker_bridge_missing_after_start",{
                                timeout_seconds:20
                            });
                        }
                    },20000);
                    workerBusy=false;'''
OLD_STATUS='''                /motor no|firma|fallo|sin respuesta|lectura fallida/i.test(v95PanelState) ?
                    "revisar V95 local" :
                workerBusy || /Iniciando|Verificando|Preparando/i.test(v95PanelState) ?
                    "iniciando local" :'''
NEW_STATUS='''                /^IA: (sin puente|motor se cerró|fallo de arranque)/.test(v95PanelState) ?
                    v95PanelState.slice(4).slice(0,37) :
                /motor no|firma|fallo|sin respuesta|lectura fallida/i.test(v95PanelState) ?
                    "revisar motor local" :
                workerBusy || /Iniciando|Verificando|Preparando|iniciando/i.test(v95PanelState) ?
                    "iniciando local" :'''

SUBSTITUTIONS=(
    ('this.addCommand("TENSHIXGAME RPG · V95","header",false);',
     'this.addCommand("IA Traductora · V95","header",false);',"TITLE"),
    ('this.addCommand("Traductor: " + localStatus,"toggle",true);',
     'this.addCommand("IA: " + localStatus,"toggle",true);',"STATUS_LABEL"),
    ('this.addCommand("Puente: " + tx710Core.getStats().lastNativeMode,',
     'this.addCommand("Ventana: " + tx710Core.getStats().lastNativeMode,',"BRIDGE_LABEL"),
    ('this.drawText("◆ TENSHIXGAME RPG · F10",0,0,185,"center");',
     'this.drawText("◆ IA Traductora · F10",0,-1,185,"center");',"MINI_LABEL"),
    ('var mini=makeNativeBase(miniX,4,208,60);',
     'var mini=makeNativeBase(miniX,4,208,46);',"MINI_HEIGHT"),
    ('        mini.opacity=215;\n        mini.refreshLabelTX=function () {',
     '''        mini.opacity=215;
        // Reduce native content padding instead of leaving an empty banner.
        if(typeof mini.createContents==="function"){
            mini.padding=6;
            mini.createContents();
        }
        mini.refreshLabelTX=function () {''',"MINI_PADDING"),
    ('            this.contents.fontSize=12;',
     '            this.contents.fontSize=14;',"MINI_FONT"),
    ('        RPGStatusMenu.prototype.constructor = RPGStatusMenu;',
     '''        RPGStatusMenu.prototype.constructor = RPGStatusMenu;
        RPGStatusMenu.prototype.standardPadding=function(){return 10;};''',"MENU_PADDING"),
    ('                    tx771BridgeAvailable(d);\n                    for(var i=0;i<obj.translations.length;i++){',
     '''                    tx771BridgeAvailable(d);
                    // Only authenticated, schema-validated /updates is READY.
                    setV95PanelState("IA: conexión local verificada");
                    for(var i=0;i<obj.translations.length;i++){''',"AUTHENTICATED_BRIDGE"),
    (OLD_SPAWN,NEW_SPAWN,"REPORT_WORKER_EXIT"),
    (OLD_STATUS,NEW_STATUS,"PANEL_FAILURE_TEXT"),
)
def replace_one(s,old,new,code):
    if s.count(old)!=1:
        raise RuntimeError("SERVIDOR_TX780_SOURCE_CONTRACT_"+code)
    return s.replace(old,new,1)
def transform(raw):
    if "\r" in raw or raw.count('var expectedHash = "')!=1:
        raise RuntimeError("SERVIDOR_TX780_WORKER_GUARD_OR_LINE_ENDING_CHANGED")
    out=raw
    for old,new,code in SUBSTITUTIONS:
        out=replace_one(out,old,new,code)
    for bad in ('"TENSHIXGAME RPG · V95"','"◆ TENSHIXGAME RPG · F10"',
                'this.addCommand("Puente: "'):
        if bad in out:raise RuntimeError("SERVIDOR_TX780_LEGACY_HUD_REMAINING")
    if out.count("worker_exited_before_bridge")!=1:
        raise RuntimeError("SERVIDOR_TX780_WORKER_EXIT_GUARD_MISSING")
    return out
def self_test():
    fixture='var expectedHash = "'+"a"*64+'";\n' + "\n".join(
        old for old,_,_ in SUBSTITUTIONS)
    modified=transform(fixture)
    assert "IA Traductora · V95" in modified
    assert "IA: sin puente local" in modified
    assert "◆ IA Traductora · F10" in modified
    assert "worker_exited_before_bridge" in modified
    try:transform(fixture.replace(OLD_SPAWN,""))
    except RuntimeError:pass
    else:raise AssertionError("SERVIDOR_TX780_WORKER_STARTUP_SOURCE_NOT_PINNED")
    print("SERVIDOR_TX780_BRAND_AND_LIVE_V95_FAILURE_PREFLIGHT_PASS")
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--self-test",action="store_true")
    ap.add_argument("--source-root",type=Path)
    args=ap.parse_args()
    if args.self_test:self_test()
    if args.source_root:
        root=args.source_root.resolve()
        head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,
             text=True,stderr=subprocess.DEVNULL).strip()
        if head!=EXPECTED_SHA:raise RuntimeError("SERVIDOR_TX780_SOURCE_SHA_CHANGED")
        target=root/TEMPLATE
        if not target.is_file() or target.is_symlink():
            raise RuntimeError("SERVIDOR_TX780_JS_SOURCE_NOT_REGULAR")
        original=target.read_bytes()
        if b"\r" in original:raise RuntimeError("SERVIDOR_TX780_INVALID_LINE_ENDINGS")
        modified=transform(original.decode("utf-8")).encode("utf-8")
        if modified==original or b"\r" in modified:
            raise RuntimeError("SERVIDOR_TX780_PATCH_INCOMPLETE")
        target.write_bytes(modified)
        print("SERVIDOR_TX780_IA_TRADUCTORA_HUD_AND_V95_WORKER_ERRORS_INTEGRATED")
    if not args.self_test and not args.source_root:
        ap.error("use --self-test or --source-root")
if __name__=="__main__":main()
