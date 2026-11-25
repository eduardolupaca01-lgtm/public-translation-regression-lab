"""R23-P2: explicit window/region OCR, local neural translation, no game edits."""
from __future__ import annotations
import ctypes, hashlib, json, os, queue, subprocess, tempfile, threading
from ctypes import wintypes
from pathlib import Path

OCR_COMMAND=r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null=[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null=[Windows.Storage.FileAccessMode,Windows.Storage,ContentType=WindowsRuntime]
$null=[Windows.Storage.Streams.IRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
$null=[Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null=[Windows.Graphics.Imaging.SoftwareBitmap,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null=[Windows.Media.Ocr.OcrEngine,Windows.Media.Ocr,ContentType=WindowsRuntime]
$null=[Windows.Media.Ocr.OcrResult,Windows.Media.Ocr,ContentType=WindowsRuntime]
$null=[Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime]
$m=[System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
 $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
 $_.GetParameters()[0].ParameterType.Name -eq ('IAsyncOperation' + [char]96 + '1')
} | Select-Object -First 1
function Await($op,[Type]$t) {
 $task=$m.MakeGenericMethod($t).Invoke($null,@($op))
 $task.Wait()
 return $task.Result
}
$lang=New-Object Windows.Globalization.Language -ArgumentList $env:IA_SCREEN_LANGUAGE
$engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
if ($null -eq $engine) { @{code='IA_OCR_IDIOMA_FALTANTE';lines=@()} | ConvertTo-Json -Compress; exit 0 }
$file=Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($env:IA_SCREEN_IMAGE)) ([Windows.Storage.StorageFile])
$stream=Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
try {
 $decoder=Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
 $bitmap=Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
 try {
  $result=Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
  @{code='OK';lines=@($result.Lines | ForEach-Object {$_.Text})} | ConvertTo-Json -Compress
 } finally { $bitmap.Dispose() }
} finally { $stream.Dispose() }
"""

def recognize(image,language):
    if language not in ("en","ja"):raise ValueError("IA_OCR_IDIOMA_INVALIDO")
    if os.name!="nt":raise RuntimeError("IA_OCR_WINDOWS_REQUERIDO")
    from PIL import Image
    image=image.convert("RGB")
    if max(image.size)>2000:image.thumbnail((2000,2000),Image.Resampling.LANCZOS)
    if min(image.size)<12:raise RuntimeError("IA_OCR_REGION_PEQUENA")
    exe=Path(os.environ.get("SystemRoot",r"C:\Windows"))/"System32"/"WindowsPowerShell"/"v1.0"/"powershell.exe"
    with tempfile.TemporaryDirectory(prefix="ia-screen-") as temp:
        filename=Path(temp)/"capture.png"
        image.save(filename)
        env=os.environ.copy()
        env.update(IA_SCREEN_IMAGE=str(filename),IA_SCREEN_LANGUAGE={"en":"en-US","ja":"ja-JP"}[language])
        try:
            result=subprocess.run([str(exe),"-NoProfile","-NonInteractive","-Command",OCR_COMMAND],
                env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),timeout=20,check=False)
        except subprocess.TimeoutExpired:raise RuntimeError("IA_OCR_TIEMPO_AGOTADO") from None
        except OSError:raise RuntimeError("IA_OCR_WINDOWS_NO_DISPONIBLE") from None
    if result.returncode!=0:raise RuntimeError("IA_OCR_WINDOWS_ERROR")
    try:doc=json.loads(result.stdout.decode("utf-8-sig"))
    except (ValueError,UnicodeError):raise RuntimeError("IA_OCR_RESPUESTA_INVALIDA") from None
    if doc.get("code")=="IA_OCR_IDIOMA_FALTANTE":raise RuntimeError("IA_OCR_IDIOMA_FALTANTE")
    lines=doc.get("lines")
    if doc.get("code")!="OK" or not isinstance(lines,list) or any(not isinstance(x,str) for x in lines):
        raise RuntimeError("IA_OCR_RESPUESTA_INVALIDA")
    return tuple(x.strip() for x in lines if x.strip())

def split_text(text,limit=1800):
    if not 1<=limit<=1800:raise ValueError("IA_OCR_LIMITE")
    parts=[]
    while len(text)>limit:
        cut=max(text.rfind(" ",0,limit),text.rfind("\n",0,limit))
        cut=cut+1 if cut>=limit//2 else limit
        parts.append(text[:cut]);text=text[cut:]
    if text:parts.append(text)
    return parts

def translate_lines(lines,language,mode,translate):
    if language not in ("en","ja") or mode not in ("dialogue","menu"):raise ValueError("IA_OCR_MODO_INVALIDO")
    original="\n".join(lines)
    blocks=lines if mode=="menu" else ((" " if language=="en" else "").join(lines),)
    output=[];failures=0
    for block in blocks:
        translated=[]
        for part in split_text(block):
            value=part.strip()
            if not value:translated.append(part);continue
            try:
                result=translate(language,value)
                if not isinstance(result,str) or not result.strip():raise ValueError("IA_OCR_VACIO")
                translated.append(result)
            except Exception:
                failures+=1;translated.append(value)
        output.append(" ".join(translated))
    return original,"\n".join(output),failures

def normalized_box(start,end,width,height):
    x0,x1=sorted((max(0,min(width,start[0])),max(0,min(width,end[0]))))
    y0,y1=sorted((max(0,min(height,start[1])),max(0,min(height,end[1]))))
    if width<=0 or height<=0 or x1-x0<12 or y1-y0<12:raise ValueError("IA_OCR_REGION_PEQUENA")
    return x0/width,y0/height,x1/width,y1/height

def pixel_box(rect,region):
    l,t,r,b=rect
    return (l+round((r-l)*region[0]),t+round((b-t)*region[1]),l+round((r-l)*region[2]),t+round((b-t)*region[3]))

def overlaps(a,b):
    return a[0]<b[2] and b[0]<a[2] and a[1]<b[3] and b[1]<a[3]

class WindowReader:
    def __init__(self):
        self.u=ctypes.windll.user32
        self.u.GetForegroundWindow.restype=wintypes.HWND
        self.u.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        self.u.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
        self.u.ClientToScreen.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.POINT)]
        self.u.IsWindow.argtypes=[wintypes.HWND]
        self.u.IsIconic.argtypes=[wintypes.HWND]
        self.u.GetAsyncKeyState.argtypes=[ctypes.c_int]
        self.u.GetAsyncKeyState.restype=ctypes.c_short
        self.u.GetSystemMetrics.argtypes=[ctypes.c_int]
    def foreground(self):return self.u.GetForegroundWindow()
    def pid(self,hwnd):
        p=wintypes.DWORD();self.u.GetWindowThreadProcessId(hwnd,ctypes.byref(p));return p.value
    def rect(self,hwnd,pid):
        if not hwnd or not self.u.IsWindow(hwnd) or self.u.IsIconic(hwnd) or self.pid(hwnd)!=pid or self.foreground()!=hwnd:return None
        r=wintypes.RECT();p=wintypes.POINT()
        if not self.u.GetClientRect(hwnd,ctypes.byref(r)) or not self.u.ClientToScreen(hwnd,ctypes.byref(p)):return None
        if not 64<=r.right<=10000 or not 64<=r.bottom<=10000:return None
        return p.x,p.y,p.x+r.right,p.y+r.bottom
    def capture(self,hwnd,pid,region,excluded=None):
        from PIL import ImageGrab
        rect=self.rect(hwnd,pid)
        if rect is None:return None
        bounds=pixel_box(rect,region)
        if excluded and overlaps(bounds,excluded):return None
        vx,vy,vw,vh=(self.u.GetSystemMetrics(n) for n in (76,77,78,79))
        if bounds[0]<vx or bounds[1]<vy or bounds[2]>vx+vw or bounds[3]>vy+vh:return None
        image=ImageGrab.grab(bbox=bounds,all_screens=True)
        if self.rect(hwnd,pid)!=rect:return None
        return image
    def f10(self):return bool(self.u.GetAsyncKeyState(0x79)&0x8000)

def run_screen(service):
    if os.name!="nt":raise RuntimeError("IA_OCR_WINDOWS_REQUERIDO")
    try:ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:ctypes.windll.user32.SetProcessDPIAware()
        except Exception:pass
    import tkinter as tk
    from tkinter import ttk
    from PIL import ImageTk
    reader=WindowReader()
    root=tk.Tk();root.title("IA Traductora - RPG - Modo visual experimental")
    root.geometry("620x480+20+20");root.minsize(420,310);root.attributes("-topmost",True)
    lang=tk.StringVar(value="en");mode=tk.StringVar(value="dialogue")
    status=tk.StringVar(value="Abre el juego normalmente. Selecciona su ventana y zona de texto.")
    selected=None;region=None;active=False;busy=False;closing=False;generation=0
    previous_key=False;candidate=None;last_display=None;last_frame=None;results=queue.Queue();jobs=[]
    top=ttk.Frame(root,padding=10);top.pack(fill="x")
    ttk.Label(top,text="IA Traductora - RPG",font=("Segoe UI",16,"bold")).pack(anchor="w")
    ttk.Label(top,text="OCR local + OPUS. No modifica archivos del juego.").pack(anchor="w")
    buttons=ttk.Frame(root,padding=(10,0));buttons.pack(fill="x")
    for label,value in (("Inglés","en"),("Japonés","ja")):ttk.Radiobutton(buttons,text=label,variable=lang,value=value).pack(side="left")
    for label,value in (("Diálogo","dialogue"),("Menú","menu")):ttk.Radiobutton(buttons,text=label,variable=mode,value=value).pack(side="left",padx=4)
    controls=ttk.Frame(root,padding=10);controls.pack(fill="x")
    body=ttk.Frame(root,padding=(10,0,10,8));body.pack(fill="both",expand=True)
    def text_area(label,lines):
        ttk.Label(body,text=label).pack(anchor="w")
        frame=ttk.Frame(body);frame.pack(fill="both",expand=True,pady=(2,6))
        widget=tk.Text(frame,wrap="word",height=lines,font=("Segoe UI",12),state="disabled")
        scroll=ttk.Scrollbar(frame,orient="vertical",command=widget.yview)
        widget.configure(yscrollcommand=scroll.set);scroll.pack(side="right",fill="y");widget.pack(side="left",fill="both",expand=True)
        return widget
    source=text_area("Texto reconocido",3);target=text_area("Español",5)
    ttk.Label(root,textvariable=status,wraplength=590,padding=10).pack(fill="x")
    def show(widget,value):
        widget.configure(state="normal");widget.delete("1.0","end");widget.insert("1.0",value);widget.configure(state="disabled")
    def invalidate(*_):
        nonlocal generation,candidate,last_display,last_frame
        generation+=1;candidate=None;last_display=None;last_frame=None
    def toggle():
        nonlocal active
        if not selected or not region:status.set("Primero selecciona la ventana y zona.");return
        active=not active;invalidate();toggle_button.configure(text="Pausar" if active else "Iniciar")
        status.set("En directo. F10 pausa/reanuda con el juego activo." if active else "Pausado. No se capturan imágenes.")
    def choose():
        nonlocal active,selected,region
        active=False;selected=None;region=None;invalidate();toggle_button.configure(text="Iniciar")
        root.withdraw()
        def ready():
            nonlocal selected,region
            if closing:return
            hwnd=reader.foreground();pid=reader.pid(hwnd) if hwnd else 0
            try:image=reader.capture(hwnd,pid,(0,0,1,1)) if pid and pid!=os.getpid() else None
            except Exception:image=None
            root.deiconify()
            if image is None:status.set("No se pudo leer la ventana. Activa el juego y prueba otra vez.");return
            selected=(hwnd,pid)
            preview=tk.Toplevel(root);preview.title("Selecciona el cuadro de diálogo o menú");preview.attributes("-topmost",True)
            image.thumbnail((max(200,min(1000,root.winfo_screenwidth()-100)),max(200,min(700,root.winfo_screenheight()-150))))
            photo=ImageTk.PhotoImage(image,master=preview);w,h=image.size
            ttk.Label(preview,text="Arrastra sobre el texto. Cierra para cancelar.").pack()
            canvas=tk.Canvas(preview,width=w,height=h,highlightthickness=0);canvas.pack()
            canvas.create_image(0,0,image=photo,anchor="nw");canvas.image=photo
            state={}
            def begin(e):
                state["start"]=(e.x,e.y)
                if "rect" in state:canvas.delete(state["rect"])
                state["rect"]=canvas.create_rectangle(e.x,e.y,e.x,e.y,outline="#00e0ff",width=3)
            def drag(e):
                if "start" in state:canvas.coords(state["rect"],*state["start"],e.x,e.y)
            def end(e):
                nonlocal region,active
                if "start" not in state:return
                try:region=normalized_box(state["start"],(e.x,e.y),w,h)
                except ValueError:return
                preview.destroy();invalidate();active=True;toggle_button.configure(text="Pausar")
                status.set("Zona seleccionada. Vuelve al juego. Mueve este panel si cubre la zona.")
            canvas.bind("<ButtonPress-1>",begin);canvas.bind("<B1-Motion>",drag);canvas.bind("<ButtonRelease-1>",end)
        root.after(3000,ready)
    ttk.Button(controls,text="Seleccionar ventana (3 s) y zona",command=choose).pack(side="left")
    toggle_button=ttk.Button(controls,text="Iniciar",command=toggle);toggle_button.pack(side="left",padx=8)
    ttk.Button(controls,text="Copiar",command=lambda:(root.clipboard_clear(),root.clipboard_append(target.get("1.0","end-1c")))).pack(side="left")
    lang.trace_add("write",invalidate);mode.trace_add("write",invalidate)
    def tick():
        nonlocal busy,candidate,last_display,last_frame,active
        if closing:return
        foreground=bool(selected and reader.foreground()==selected[0] and reader.pid(selected[0])==selected[1])
        try:
            while True:
                g,kind,payload=results.get_nowait();busy=False
                if g!=generation or not active or not foreground:continue
                if kind=="error":
                    active=False;toggle_button.configure(text="Iniciar")
                    status.set("Instala reconocimiento OCR del idioma desde Configuración de Windows." if payload=="IA_OCR_IDIOMA_FALTANTE" else "OCR: "+payload);continue
                lines,digest,translated=payload;last_frame=digest
                if not lines:
                    candidate=None;last_display=None;show(source,"");show(target,"");status.set("Sin texto en la zona.");continue
                candidate=lines
                if translated is not None:
                    original,spanish,failures=translated;last_display=lines
                    show(source,original);show(target,spanish)
                    status.set("Partes sin traducir: "+str(failures) if failures else "Traducción local lista. F10 pausa/reanuda.")
        except queue.Empty:pass
        if active and selected and region and not busy and foreground:
            try:
                excluded=None
                if root.state()=="normal":
                    x,y=root.winfo_rootx(),root.winfo_rooty();excluded=(x-8,y-35,x+root.winfo_width()+8,y+root.winfo_height()+8)
                image=reader.capture(*selected,region,excluded=excluded)
                if image is None:status.set("Zona no visible o cubierta por el panel. Mueve el panel y activa el juego.")
                else:
                    digest=hashlib.sha256(image.tobytes()).digest();stable=candidate;cached_frame=digest==last_frame
                    if not (cached_frame and (candidate is None or candidate==last_display)):
                        busy=True;g=generation;language=lang.get();presentation=mode.get();displayed=last_display
                        def work():
                            try:
                                lines=stable if cached_frame else recognize(image,language)
                                translation=translate_lines(lines,language,presentation,service.translate) if lines and lines==stable and lines!=displayed else None
                                results.put((g,"ok",(lines,digest,translation)))
                            except Exception as e:
                                code=str(e);results.put((g,"error",code if code.startswith("IA_OCR_") and len(code)<90 else "IA_OCR_ERROR_LOCAL"))
                        thread=threading.Thread(target=work,daemon=True);jobs[:]=[thread];thread.start()
            except Exception:status.set("No se pudo capturar la zona. Selecciónala nuevamente.")
        root.after(300,tick)
    def close():
        nonlocal closing,active
        closing=True;active=False;invalidate();root.destroy()
    def poll_f10():
        nonlocal previous_key
        if closing:return
        focus=bool(selected and reader.foreground()==selected[0] and reader.pid(selected[0])==selected[1])
        key=reader.f10() if focus else False
        if key and not previous_key and region:toggle()
        previous_key=key
        root.after(35,poll_f10)
    root.bind("<F10>",lambda event:toggle())
    root.protocol("WM_DELETE_WINDOW",close);root.after(250,tick);root.after(35,poll_f10);root.mainloop()
    for job in jobs:job.join()

def screen_selftest(neural):
    from PIL import Image,ImageDraw,ImageFont
    image=Image.new("RGB",(1000,150),"white")
    font=ImageFont.truetype(str(Path(os.environ.get("SystemRoot",r"C:\Windows"))/"Fonts"/"arial.ttf"),42)
    ImageDraw.Draw(image).text((15,35),"Good morning. How are you?",fill="black",font=font)
    code="IA_OCR_AUTOPRUEBA_REAL_LISTA"
    try:
        lines=recognize(image,"en")
        if "good morning" not in " ".join(lines).lower():raise RuntimeError("IA_OCR_AUTOPRUEBA_TEXTO")
    except RuntimeError as e:
        if str(e)!="IA_OCR_IDIOMA_FALTANTE":raise
        lines=("Good morning. How are you?",);code="IA_OCR_AUTOPRUEBA_MODELO_LISTO_IDIOMA_FALTANTE"
    original,spanish,failures=translate_lines(lines,"en","dialogue",neural.translate)
    if failures or not spanish or spanish==original:raise RuntimeError("IA_OCR_AUTOPRUEBA_TRADUCCION")
    return code
