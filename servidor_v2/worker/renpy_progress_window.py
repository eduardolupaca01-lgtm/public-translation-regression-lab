"""A local, non-modal Win32 progress window owned by the Ren'Py worker.
No interaction with the game thread, game windows, external services or input.
Closing live view does not stop translation; closing preparation requests cancellation.
"""
import os
import re
import threading

SCHEMA="ia-renpy-progress-window-v1"
CLASS_PREFIX="IA_RENPY_PROGRESS_"

class ProgressWindow:
    def __init__(self,side,service,read_json,atomic_json):
        self.side=side;self.service=service
        self.read_json=read_json;self.atomic_json=atomic_json
        self.thread=None;self.hwnd=None;self.stop=threading.Event()
        self.user=None;self.created=False
    def mark(self,state):
        try:self.atomic_json(self.side/"window-status.json",{"schema":SCHEMA,"state":state,"pid":os.getpid()})
        except OSError:pass
    def start(self):
        if os.name!="nt" or self.thread is not None:return
        self.thread=threading.Thread(target=self.run,daemon=True,name="IA-RenPy-ProgressWindow")
        self.thread.start()
    def close(self):
        self.stop.set()
        hwnd=self.hwnd
        if hwnd and self.user:
            self.user.PostMessageW(hwnd,0x0010,0,0)
        if self.thread is not None:self.thread.join(timeout=2)
    def lines(self):
        try:
            p=self.read_json(self.side/"client-progress.json",8192)
            if p.get("schema")!="ia-servidor-renpy-v1":p={}
        except (OSError,ValueError,TypeError):p={}
        def count(key):
            value=p.get(key,0)
            return value if type(value) is int and 0<=value<2**53 else 0
        state=self.service.status()
        phases={"ESCANEO":"Escaneando textos","CONECTANDO":"Conectando motor local",
                "ESPERANDO_MOTOR":"Esperando motor local","TRADUCIENDO":"Traduciendo en segundo plano","LISTO":"Cola al día"}
        scan=p.get("scan",{})
        files=scan.get("script_files",0) if isinstance(scan,dict) else 0
        if type(files) is not int or not 0<=files<2**53:files=0
        phase=phases.get(p.get("phase"),"IA Traductora iniciada")
        if p.get("preparation_id"):phase="Preparación previa: "+phase
        return (
            phase,
            "Archivos: {:,} | Textos detectados: {:,}".format(files,count("discovered")),
            "Nuevas: {:,} | Memoria: {:,}".format(state["translated"],state["cached"]+count("preloaded")),
            "Pendientes: {:,} | Sin cambio: {:,}".format(count("pending"),count("unchanged")),
            "Errores: {:,} | Aplicaciones: {:,}".format(count("transport_failed"),count("applied")),
            "Cierra para detener la preparación." if p.get("preparation_id") else "Puedes cerrar esta ventana; la traducción continúa.",
        )
    def run(self):
        try:self.run_native()
        except Exception:
            self.mark("unavailable")
    def run_native(self):
        import ctypes as C
        from ctypes import wintypes as W
        user=C.WinDLL("user32",use_last_error=True);self.user=user
        kernel=C.WinDLL("kernel32",use_last_error=True)
        gdi=C.WinDLL("gdi32",use_last_error=True)
        H=C.c_void_p;LRESULT=C.c_ssize_t;WPARAM=C.c_size_t;LPARAM=C.c_ssize_t
        WNDPROC=C.WINFUNCTYPE(LRESULT,H,C.c_uint,WPARAM,LPARAM)
        class WNDCLASS(C.Structure):
            _fields_=[("style",C.c_uint),("lpfnWndProc",WNDPROC),("cbClsExtra",C.c_int),("cbWndExtra",C.c_int),
                      ("hInstance",H),("hIcon",H),("hCursor",H),("hbrBackground",H),
                      ("lpszMenuName",C.c_wchar_p),("lpszClassName",C.c_wchar_p)]
        class POINT(C.Structure):
            _fields_=[("x",C.c_long),("y",C.c_long)]
        class MSG(C.Structure):
            _fields_=[("hwnd",H),("message",C.c_uint),("wParam",WPARAM),("lParam",LPARAM),
                      ("time",C.c_uint32),("pt",POINT),("lPrivate",C.c_uint32)]
        def bind(lib,name,ret,args):
            fn=getattr(lib,name);fn.restype=ret;fn.argtypes=args;return fn
        defproc=bind(user,"DefWindowProcW",LRESULT,[H,C.c_uint,WPARAM,LPARAM])
        reg=bind(user,"RegisterClassW",C.c_ushort,[C.POINTER(WNDCLASS)])
        unreg=bind(user,"UnregisterClassW",W.BOOL,[C.c_wchar_p,H])
        create=bind(user,"CreateWindowExW",H,[C.c_uint32,C.c_wchar_p,C.c_wchar_p,C.c_uint32,
                    C.c_int,C.c_int,C.c_int,C.c_int,H,H,H,H])
        destroy=bind(user,"DestroyWindow",W.BOOL,[H])
        show=bind(user,"ShowWindow",W.BOOL,[H,C.c_int])
        settext=bind(user,"SetWindowTextW",W.BOOL,[H,C.c_wchar_p])
        send=bind(user,"SendMessageW",LRESULT,[H,C.c_uint,WPARAM,LPARAM])
        bind(user,"PostMessageW",W.BOOL,[H,C.c_uint,WPARAM,LPARAM])
        timer=bind(user,"SetTimer",C.c_size_t,[H,C.c_size_t,C.c_uint,H])
        killtimer=bind(user,"KillTimer",W.BOOL,[H,C.c_size_t])
        quitmsg=bind(user,"PostQuitMessage",None,[C.c_int])
        getmsg=bind(user,"GetMessageW",C.c_int,[C.POINTER(MSG),H,C.c_uint,C.c_uint])
        translate=bind(user,"TranslateMessage",W.BOOL,[C.POINTER(MSG)])
        dispatch=bind(user,"DispatchMessageW",LRESULT,[C.POINTER(MSG)])
        module=bind(kernel,"GetModuleHandleW",H,[C.c_wchar_p])
        stock=bind(gdi,"GetStockObject",H,[C.c_int])
        instance=module(None)
        name=CLASS_PREFIX+str(os.getpid())
        fields=[]
        last=[None]
        def paint_values():
            values=self.lines()
            if values==last[0]:return
            last[0]=values
            for control,value in zip(fields,values):settext(control,value)
        @WNDPROC
        def proc(hwnd,msg,wp,lp):
            try:
                if msg==0x0113 and wp==1:
                    if self.stop.is_set():destroy(hwnd)
                    else:paint_values()
                    return 0
                if msg==0x0010:
                    # Closing a regular live view does not stop the motor.
                    # In the explicitly requested preparation mode, close
                    # is a cancellation request, matched to this ticket.
                    try:
                        p=self.read_json(self.side/"client-progress.json",8192)
                        ticket=self.read_json(self.side/"prepare-request.json",4096)
                        nonce=p.get("preparation_id","")
                        if not self.stop.is_set() and re.fullmatch("[0-9a-f]{32}",nonce) and ticket.get("schema")=="ia-servidor-renpy-v1" and ticket.get("id")==nonce:
                            try:
                                with (self.side/("prepare-cancel-"+nonce+".txt")).open("x",encoding="ascii") as marker:marker.write("cancel")
                            except FileExistsError:pass
                    except (OSError,ValueError,TypeError):pass
                    destroy(hwnd);return 0
                if msg==0x0002:
                    killtimer(hwnd,1);quitmsg(0);return 0
            except Exception:pass
            return defproc(hwnd,msg,wp,lp)
        wc=WNDCLASS()
        wc.lpfnWndProc=proc;wc.hInstance=instance;wc.hbrBackground=H(6)
        wc.lpszClassName=name
        if not reg(C.byref(wc)):raise OSError("progress window registration")
        try:
            if self.stop.is_set():return
            # Standard non-topmost window; it never steals keyboard focus.
            hwnd=create(0x00040000,name,"IA Traductora - Ren'Py",0x00CA0000,
                        36,36,460,224,None,None,instance,None)
            if not hwnd:raise OSError("progress window creation")
            self.hwnd=hwnd
            font=stock(17)
            for i in range(6):
                child=create(0,"STATIC","",0x50000000,16,12+i*27,420,23,hwnd,None,instance,None)
                if not child:raise OSError("progress label creation")
                fields.append(child)
                if font:send(child,0x0030,font,1)
            paint_values()
            if not timer(hwnd,1,750,None):raise OSError("progress timer")
            show(hwnd,4) # SW_SHOWNOACTIVATE
            self.created=True;self.mark("visible")
            msg=MSG()
            while getmsg(C.byref(msg),None,0,0)>0:
                translate(C.byref(msg));dispatch(C.byref(msg))
            self.mark("closed")
        finally:
            hwnd=self.hwnd;self.hwnd=None
            if hwnd:destroy(hwnd)
            unreg(name,instance)
