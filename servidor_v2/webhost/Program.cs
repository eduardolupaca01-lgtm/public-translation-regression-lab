using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace IAWebPlayer {
  internal sealed class Receipt {
    public string schema {get;set;}
    public int port {get;set;}
    public string index_sha256 {get;set;}
    public Dictionary<string,string> engine_sha256 {get;set;}
    public Dictionary<string,string> host_sha256 {get;set;}
  }
  internal static class Program {
    internal static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
    internal static readonly string Root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
    internal static readonly string Rpg = Path.Combine(Root,"IA Traductora",".local","Rpg");
    internal static readonly string Engine = Path.Combine(Rpg,"engine");
    internal static readonly string[] Hosts={"Jugar-IA.exe","Jugar-IA.exe.config","Microsoft.Web.WebView2.Core.dll",
      "Microsoft.Web.WebView2.WinForms.dll","WebView2Loader.dll","WebView2-LICENSE.txt"};

    internal static string Code(Exception ex) {
      var m=Regex.Match(ex.Message??"",@"^IA_[A-Z0-9_]{4,90}$");
      return m.Success?m.Value:"IA_WEB_DESKTOP_ERROR";
    }
    internal static void CheckPath(string path,bool directory) {
      var at=Path.GetFullPath(path);
      for(bool first=true;;first=false) {
        var attr=File.GetAttributes(at);
        if((attr&FileAttributes.ReparsePoint)!=0 ||
           (((attr&FileAttributes.Directory)!=0)!=(first?directory:true)))
          throw new InvalidOperationException("IA_WEB_DESKTOP_RUTA_INSEGURA");
        var parent=Path.GetDirectoryName(at);
        if(String.IsNullOrEmpty(parent)||parent==at)break;
        at=parent;
      }
    }
    internal static string Hash(string path) {
      CheckPath(path,false);
      using(var f=File.OpenRead(path))
      using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(f)).Replace("-","").ToLowerInvariant();
    }
    internal static string ReadSmall(string path,int limit) {
      CheckPath(path,false);
      using(var f=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete)){
        if(f.Length<=0||f.Length>limit)throw new InvalidOperationException("IA_WEB_DESKTOP_MANIFIESTO_INVALIDO");
        using(var reader=new StreamReader(f))return reader.ReadToEnd();
      }
    }
    static bool SafeEngineName(string name){
      if(String.IsNullOrEmpty(name)||name.Length>200||name.Contains("\\")||name.Contains(":"))return false;
      foreach(var part in name.Split('/'))
        if(part==""||part=="."||part==".."||part.EndsWith(".")||part.EndsWith(" ")||
           !Regex.IsMatch(part,@"^[A-Za-z0-9_.-]+$"))return false;
      return true;
    }
    internal static Receipt Validate() {
      CheckPath(Root,true);CheckPath(Engine,true);
      if(File.Exists(Path.Combine(Root,"IA_COPIA_WEB_INCOMPLETA.txt")))
        throw new InvalidOperationException("IA_WEB_COPIA_INCOMPLETA");
      var r=Json.Deserialize<Receipt>(ReadSmall(Path.Combine(Root,"web-copy-v1.json"),16384));
      if(r==null||r.schema!="ia-web-desktop-v1"||r.port<1024||r.port>65535||
         r.host_sha256==null||r.host_sha256.Count!=Hosts.Length||r.engine_sha256==null||
         r.engine_sha256.Count>65)
        throw new InvalidOperationException("IA_WEB_DESKTOP_MANIFIESTO_INVALIDO");
      foreach(var name in Hosts) {
        if(!r.host_sha256.ContainsKey(name)||Hash(Path.Combine(Root,name))!=r.host_sha256[name])
          throw new InvalidOperationException("IA_WEB_HOST_SHA_INVALIDO");
      }
      foreach(var name in new[]{"IATraductora.exe","models/opus_en_es/model.bin","models/opus_ja_es/model.bin"})
        if(!r.engine_sha256.ContainsKey(name))throw new InvalidOperationException("IA_WEB_DESKTOP_MOTOR_INCOMPLETO");
      foreach(var entry in r.engine_sha256){
        if(!SafeEngineName(entry.Key)||!Regex.IsMatch(entry.Value??"",@"^[a-f0-9]{64}$")||
           Hash(Path.Combine(Engine,entry.Key.Replace('/',Path.DirectorySeparatorChar)))!=entry.Value)
          throw new InvalidOperationException("IA_WEB_DESKTOP_MOTOR_SHA_INVALIDO");
      }
      if(Hash(Path.Combine(Root,"index.html"))!=r.index_sha256)
        throw new InvalidOperationException("IA_WEB_DESKTOP_RECURSO_CAMBIADO");
      return r;
    }
    [STAThread] static int Main(string[] args) {
      // Fixed acceptance actions only on an explicitly selected synthetic QA fixture.
      // The normal launcher accepts no external URL, script, or process name.
      bool qa=args.Length==1&&(args[0]=="--qa"||args[0]=="--qa-reopen")&&
              Environment.GetEnvironmentVariable("IA_WEB_DESKTOP_QA")=="1";
      try {
        if(args.Length!=0&&!qa)throw new InvalidOperationException("IA_WEB_DESKTOP_ARGUMENTOS_INVALIDOS");
        var receipt=Validate();
        if(qa&&!ReadSmall(Path.Combine(Root,"assets","main.js"),32768).Contains("fixture-save"))
          throw new InvalidOperationException("IA_WEB_DESKTOP_QA_FIXTURE_INVALIDO");
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        using(var form=new Player(receipt,qa?args[0]:"")) {
          Application.Run(form);return form.ExitCode;
        }
      }catch(Exception ex){
        var code=Code(ex);
        if(qa){try{File.WriteAllText(Path.Combine(Rpg,"web-qa-result.txt"),code);}catch{}}
        else MessageBox.Show("No se pudo abrir la copia web.\n"+code,"IA Traductora",MessageBoxButtons.OK,MessageBoxIcon.Error);
        return 1;
      }
    }
  }

  internal sealed class Player:Form {
    readonly Receipt receipt;
    readonly string qa,origin,startupFile;
    readonly HttpClient http=new HttpClient(new HttpClientHandler{UseProxy=false});
    readonly CancellationTokenSource cancel=new CancellationTokenSource();
    readonly WebView2 view=new WebView2{Dock=DockStyle.Fill,Visible=false};
    readonly Label notice=new Label{Dock=DockStyle.Fill,TextAlign=ContentAlignment.MiddleCenter,Text="Preparando IA Traductora y OPUS local..."};
    readonly System.Windows.Forms.Timer lifetime=new System.Windows.Forms.Timer{Interval=500};
    Process worker;
    FileStream sessionLock;
    string token;
    bool closing,closed;
    public int ExitCode {get;private set;}
    public Player(Receipt r,string qaMode){
      receipt=r;qa=qaMode;origin="http://127.0.0.1:"+r.port;
      startupFile=Path.Combine(Program.Rpg,"web-native-"+Guid.NewGuid().ToString("N")+".json");
      Text="Juego · IA Traductora";Width=1120;Height=760;MinimumSize=new Size(640,400);
      StartPosition=FormStartPosition.CenterScreen;
      Controls.Add(view);Controls.Add(notice);
      http.Timeout=TimeSpan.FromSeconds(3);
      Shown+=async(s,e)=>await BeginAsync();
      FormClosing+=CloseAsync;
      lifetime.Tick+=(s,e)=>{if(worker!=null&&worker.HasExited&&!closing)Close();};
    }
    static string Quote(string value) {
      if(value.IndexOf('"')>=0||value.EndsWith("\\"))throw new InvalidOperationException("IA_WEB_DESKTOP_RUTA_INSEGURA");
      return "\""+value+"\"";
    }
    async Task BeginAsync() {
      try {
        string lockPath=Path.Combine(Program.Rpg,"web-desktop.lock");
        if(File.Exists(lockPath))Program.CheckPath(lockPath,false);
        try{sessionLock=new FileStream(lockPath,FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);}
        catch(IOException){throw new InvalidOperationException("IA_WEB_DESKTOP_YA_ABIERTO");}
        string profile=Path.Combine(Program.Rpg,"webview-profile");
        if(!Directory.Exists(profile))Directory.CreateDirectory(profile);
        Program.CheckPath(profile,true);
        CoreWebView2Environment environment;
        try{environment=await CoreWebView2Environment.CreateAsync(null,profile);}
        catch(Exception){throw new InvalidOperationException("IA_WEB_DESKTOP_WEBVIEW2_NO_DISPONIBLE");}
        if(closing)return;
        var c=cancel.Token;
        var info=new ProcessStartInfo{
          FileName=Path.Combine(Program.Engine,"IATraductora.exe"),
          Arguments="--web-root "+Quote(Program.Root)+" --web-port "+receipt.port+
            " --web-no-browser --parent-pid "+Process.GetCurrentProcess().Id+" --diagnostic-file "+Quote(startupFile),
          WorkingDirectory=Program.Root,UseShellExecute=false,CreateNoWindow=true
        };
        worker=Process.Start(info);
        var watch=Stopwatch.StartNew();
        while(watch.Elapsed<TimeSpan.FromSeconds(180)){
          c.ThrowIfCancellationRequested();
          string code="";
          if(File.Exists(startupFile)){
            var status=Program.Json.Deserialize<Dictionary<string,string>>(Program.ReadSmall(startupFile,1024));
            if(status.ContainsKey("code")&&Regex.IsMatch(status["code"],@"^IA_[A-Z0-9_]{4,86}$"))code=status["code"];
          }
          if(worker.HasExited)throw new InvalidOperationException(code==""?"IA_WEB_DESKTOP_OPUS_NO_INICIA":code);
          if(code=="IA_WEB_LISTO"){
            try{
              var text=await http.GetStringAsync(origin+"/__ia/adapter.js");
              var m=Regex.Match(text,"const token=\"([a-f0-9]{64})\";");
              if(m.Success){token=m.Groups[1].Value;break;}
            }catch(HttpRequestException){}catch(TaskCanceledException){}
          }
          await Task.Delay(200,c);
        }
        if(token==null)throw new InvalidOperationException("IA_WEB_DESKTOP_OPUS_TIMEOUT");
        await view.EnsureCoreWebView2Async(environment);
        if(closing)return;
        var core=view.CoreWebView2;
        core.Settings.AreDevToolsEnabled=false;
        core.Settings.AreDefaultContextMenusEnabled=false;
        core.Settings.AreHostObjectsAllowed=false;
        core.Settings.IsWebMessageEnabled=false;
        core.Settings.IsPasswordAutosaveEnabled=false;
        core.Settings.IsGeneralAutofillEnabled=false;
        view.AllowExternalDrop=false;
        core.NavigationStarting+=(s,e)=>{if(!Local(e.Uri))e.Cancel=true;};
        core.FrameNavigationStarting+=(s,e)=>{if(!Local(e.Uri)&&e.Uri!="about:blank")e.Cancel=true;};
        core.NewWindowRequested+=(s,e)=>e.Handled=true;
        core.DownloadStarting+=(s,e)=>{e.Cancel=true;e.Handled=true;};
        core.PermissionRequested+=(s,e)=>{e.State=CoreWebView2PermissionState.Deny;};
        core.AddWebResourceRequestedFilter("*",CoreWebView2WebResourceContext.All);
        core.WebResourceRequested+=(s,e)=>{
          string uri=e.Request.Uri;
          if(!Local(uri)&&!uri.StartsWith("data:",StringComparison.OrdinalIgnoreCase)&&
             !uri.StartsWith("blob:"+origin+"/",StringComparison.OrdinalIgnoreCase))
            e.Response=environment.CreateWebResourceResponse(new MemoryStream(),403,"Forbidden","Content-Type: text/plain");
        };
        notice.Visible=false;view.Visible=true;view.BringToFront();
        core.Navigate(origin+"/#/");
        lifetime.Start();
        if(qa!="")await RunQa(core,c);
      }catch(OperationCanceledException){if(!closing){Fail("IA_WEB_DESKTOP_CANCELADO");Close();}}
       catch(Exception ex){if(!closing){Fail(Program.Code(ex));Close();}}
    }
    bool Local(string value){
      Uri u;
      return Uri.TryCreate(value,UriKind.Absolute,out u)&&u.Scheme=="http"&&u.Host=="127.0.0.1"&&u.Port==receipt.port&&String.IsNullOrEmpty(u.UserInfo);
    }
    void Fail(string code) {
      ExitCode=1;
      if(qa!=""){try{File.WriteAllText(Path.Combine(Program.Rpg,"web-qa-result.txt"),code);}catch{}}
      else MessageBox.Show(this,"No se pudo iniciar IA Traductora.\n"+code+
       "\nSi el puerto está ocupado, cierra la otra copia. Si falta WebView2, instala el runtime oficial de Microsoft.",
       "IA Traductora",MessageBoxButtons.OK,MessageBoxIcon.Error);
    }
    async void CloseAsync(object sender,FormClosingEventArgs e){
      if(closed)return;
      e.Cancel=true;
      if(closing)return;
      closing=true;lifetime.Stop();cancel.Cancel();
      try{
        view.Visible=false;view.Dispose();
        if(worker!=null&&!worker.HasExited&&token!=null){
          try{
            using(var request=new HttpRequestMessage(HttpMethod.Post,origin+"/__ia/stop")){
              request.Headers.TryAddWithoutValidation("Origin",origin);
              request.Headers.TryAddWithoutValidation("X-IA-Token",token);
              request.Content=new StringContent("{}");
              using(var response=await http.SendAsync(request)){}
            }
          }catch(HttpRequestException){}catch(TaskCanceledException){}
          if(!await Task.Run(()=>worker.WaitForExit(35000)))ExitCode=1;
        }
        // On startup failure/early close the worker follows this parent's
        // real Windows HANDLE and will exit; never terminate other programs.
        if(worker!=null&&worker.HasExited&&worker.ExitCode!=0)ExitCode=1;
      }catch(Exception){ExitCode=1;}
      finally{
        if(sessionLock!=null)sessionLock.Dispose();
        if(worker!=null)worker.Dispose();
        http.Dispose();
        try{if(File.Exists(startupFile))File.Delete(startupFile);}catch(IOException){}
        closed=true;
        // Queue the final close, rather than recursing into FormClosing.
        BeginInvoke(new Action(Close));
      }
    }
    // Explicit CI-only fixed interactions on the synthetic fixture. No
    // arbitrary script input or native binding is exposed to the page.
    async Task<string> Read(CoreWebView2 core,string expression){
      return Program.Json.Deserialize<string>(await core.ExecuteScriptAsync(expression));
    }
    async Task WaitText(CoreWebView2 core,string term,CancellationToken c){
      var watch=Stopwatch.StartNew();
      while(watch.Elapsed<TimeSpan.FromSeconds(100)){
        c.ThrowIfCancellationRequested();
        var t=await Read(core,"document.querySelector('#dialog')?.textContent ?? ''");
        if(t!=null&&t.IndexOf(term,StringComparison.OrdinalIgnoreCase)>=0)return;
        await Task.Delay(120,c);
      }
      throw new InvalidOperationException("IA_WEB_DESKTOP_QA_TEXTO_TIMEOUT");
    }
    async Task RunQa(CoreWebView2 core,CancellationToken c){
      if(qa=="--qa"){
        await WaitText(core,"ventana",c);
        if(await Read(core,"document.querySelector('#next')?.textContent")!="Siguiente"||
           await Read(core,"document.querySelector('#save')?.textContent")!="Guardar"||
           await Read(core,"document.querySelector('#name')?.value")!="Please keep my name."||
           await Read(core,"document.querySelector('#identity')?.textContent")!="Alice")
          throw new InvalidOperationException("IA_WEB_DESKTOP_QA_CONTROLES");
        await core.ExecuteScriptAsync("document.querySelector('#next').click()");
        await WaitText(core,"puente",c);
        await core.ExecuteScriptAsync("document.querySelector('#save').click()");
        if(await Read(core,"localStorage.getItem('fixture-save')")!="1")
          throw new InvalidOperationException("IA_WEB_DESKTOP_QA_GUARDADO");
        await core.ExecuteScriptAsync("window.dispatchEvent(new KeyboardEvent('keydown',{key:'F10'}))");
        if(await Read(core,"String(document.querySelector('#ia-web-panel')?.hidden)")!="false")
          throw new InvalidOperationException("IA_WEB_DESKTOP_QA_F10");
        File.WriteAllText(Path.Combine(Program.Rpg,"web-qa-result.txt"),"IA_WEB_DESKTOP_NATIVE_QA_PASS");
      }else{
        await WaitText(core,"puente",c);
        if(await Read(core,"localStorage.getItem('fixture-save')")!="1")
          throw new InvalidOperationException("IA_WEB_DESKTOP_QA_GUARDADO");
        File.WriteAllText(Path.Combine(Program.Rpg,"web-qa-result.txt"),"IA_WEB_DESKTOP_REOPEN_QA_PASS");
      }
      Close();
    }
  }
}
