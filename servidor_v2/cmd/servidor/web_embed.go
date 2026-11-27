package main

// Read-only extractor for the standard 64-bit Go embed.FS layout used by
// Wails v2. Independently implemented against the Go 1.23 compiler contract:
// https://github.com/golang/go/blob/go1.23.6/src/cmd/compile/internal/staticdata/embed.go
// https://github.com/golang/go/blob/go1.23.6/src/cmd/compile/internal/staticdata/data.go
// https://github.com/golang/go/blob/go1.23.6/src/cmd/internal/notsha256/sha256.go
// Never load/execute a PE, alter its contents, search process memory, or guess
// encryption keys. Unsupported packers and native dependencies fail closed.
import (
 "bytes"
 "crypto/sha256"
 "encoding/binary"
 "errors"
 "io"
 "io/fs"
 "os"
 "path"
 "path/filepath"
 "strings"
 "unicode"
 "unicode/utf8"
)

const webEmbedMaxEXE=int64(2*1024*1024*1024-1)
const webEmbedMaxEntries=20000
const webEmbedChunk=4*1024*1024
type webPERegion struct{va,size uint64;off int64}
type webEmbedMember struct{name string;off,size int64;sum [16]byte;dir bool}
type webEmbedPlan struct{members []webEmbedMember;total uint64}
func webU64(b []byte)uint64{return binary.LittleEndian.Uint64(b)}
func webU32(b []byte)uint32{return binary.LittleEndian.Uint32(b)}
func webU16(b []byte)uint16{return binary.LittleEndian.Uint16(b)}
func webReadAt(f io.ReaderAt,off int64,n int)([]byte,error){
 b:=make([]byte,n)
 _,e:=f.ReadAt(b,off)
 if e!=nil{return nil,e}
 return b,nil
}
func webPERegions(f io.ReaderAt,size int64)([]webPERegion,error){
 invalid:=errors.New("IA_WEB_EXE_FORMATO_NO_ADMITIDO")
 if size<256||size>webEmbedMaxEXE{return nil,invalid}
 dos,e:=webReadAt(f,0,64)
 if e!=nil||string(dos[:2])!="MZ"{return nil,invalid}
 pe:=int64(webU32(dos[60:64]))
 if pe<64||pe>1024*1024||pe+24>size{return nil,invalid}
 coff,e:=webReadAt(f,pe,24)
 if e!=nil||string(coff[:4])!="PE\x00\x00"||webU16(coff[4:6])!=0x8664{return nil,invalid}
 count:=int(webU16(coff[6:8]));opts:=int(webU16(coff[20:22]))
 if count<1||count>96||opts<112||opts>4096||pe+24+int64(opts+40*count)>size{return nil,invalid}
 headers,e:=webReadAt(f,pe+24,opts+40*count)
 if e!=nil||webU16(headers[:2])!=0x20b{return nil,invalid}
 base:=webU64(headers[24:32])
 if base==0||base>^uint64(0)-0x200000000{return nil,invalid}
 regions:=make([]webPERegion,0,count)
 for i:=0;i<count;i++{
  s:=headers[opts+40*i:opts+40*(i+1)]
  flags:=webU32(s[36:40])
  if flags&0x40==0||flags&0x40000000==0||flags&0x20000000!=0{continue}
  raw:=uint64(webU32(s[16:20]));virtual:=uint64(webU32(s[8:12]))
  off:=int64(webU32(s[20:24]));va:=base+uint64(webU32(s[12:16]))
  if raw==0{continue}
  if off<=0||raw>uint64(size)||off>size-int64(raw){return nil,invalid}
  if virtual>0&&virtual<raw{raw=virtual}
  if va%8!=0{return nil,invalid}
  for _,r:=range regions{
   if va<r.va+r.size&&r.va<va+raw{return nil,invalid}
  }
  regions=append(regions,webPERegion{va,raw,off})
 }
 if len(regions)==0{return nil,invalid}
 return regions,nil
}
func webPEOffset(regions []webPERegion,va,n uint64)(int64,bool){
 for _,r:=range regions{
  if va>=r.va&&va-r.va<=r.size&&n<=r.size-(va-r.va){return r.off+int64(va-r.va),true}
 }
 return 0,false
}
// Validate portable path names before any host filesystem operation.
func webEmbedSafeName(name string)bool{
 if name==""||len(name)>1024||!utf8.ValidString(name)||!fs.ValidPath(name)||name=="."||
    strings.ContainsAny(name,"\\:<>\"|?*"){return false}
 for _,c:=range name{if unicode.IsControl(c){return false}}
 for _,part:=range strings.Split(name,"/"){
  if len(part)>240||strings.HasSuffix(part,".")||strings.HasSuffix(part," "){return false}
  stem:=strings.ToUpper(strings.TrimSpace(strings.SplitN(part,".",2)[0]))
  if stem=="CON"||stem=="PRN"||stem=="AUX"||stem=="NUL"||stem=="CONIN$"||stem=="CONOUT$"{return false}
  if len(stem)==4&&(strings.HasPrefix(stem,"COM")||strings.HasPrefix(stem,"LPT"))&&stem[3]>='1'&&stem[3]<='9'{return false}
  if strings.HasPrefix(stem,"COM")||strings.HasPrefix(stem,"LPT"){
   if strings.ContainsAny(stem,"¹²³"){return false}
  }
 }
 return true
}
func webEmbedReadTable(f io.ReaderAt,regions []webPERegion,va,count uint64)([]webEmbedMember,bool){
 if count<3||count>webEmbedMaxEntries{return nil,false}
 off,ok:=webPEOffset(regions,va,count*48)
 if !ok{return nil,false}
 table,e:=webReadAt(f,off,int(count*48))
 if e!=nil{return nil,false}
 members:=make([]webEmbedMember,0,count)
 seen:=make(map[string]bool)
 lastDir,lastBase:="",""
 for i:=uint64(0);i<count;i++{
  row:=table[i*48:(i+1)*48]
  n:=webU64(row[8:16])
  if n==0||n>1024{return nil,false}
  noff,ok:=webPEOffset(regions,webU64(row[:8]),n)
  if !ok{return nil,false}
  raw,e:=webReadAt(f,noff,int(n));if e!=nil{return nil,false}
  name:=string(raw);dir:=strings.HasSuffix(name,"/");name=strings.TrimSuffix(name,"/")
  if !webEmbedSafeName(name)||seen[name]{return nil,false}
  seen[name]=true
  d,b:=path.Dir(name),path.Base(name)
  if i>0&&(d<lastDir||(d==lastDir&&b<=lastBase)){return nil,false}
  lastDir,lastBase=d,b
  data,lenData:=webU64(row[16:24]),webU64(row[24:32])
  var sum [16]byte;copy(sum[:],row[32:48])
  m:=webEmbedMember{name:name,dir:dir,size:int64(lenData),sum:sum}
  if dir{
   if data!=0||lenData!=0||sum!=([16]byte{}){return nil,false}
  }else{
   if lenData>uint64(webEmbedMaxEXE)||sum==([16]byte{}){return nil,false}
   if lenData!=0{
    m.off,ok=webPEOffset(regions,data,lenData);if !ok{return nil,false}
   }
  }
  members=append(members,m)
 }
 // Real embed.FS tables include their parent directories.
 dirs:=map[string]bool{".":true}
 for _,m:=range members{if m.dir{dirs[m.name]=true}}
 for _,m:=range members{if !dirs[path.Dir(m.name)]{return nil,false}}
 return members,true
}
func webEmbedProfile(f io.ReaderAt,members []webEmbedMember)([]webEmbedPlan,bool){
 plans:=[]webEmbedPlan{}
 for _,idx:=range members{
  if idx.dir||path.Base(idx.name)!="index.html"||idx.size<1||idx.size>1024*1024{continue}
  root:=path.Dir(idx.name);prefix:=""
  if root!="."{prefix=root+"/"}
  raw,e:=webReadAt(f,idx.off,int(idx.size));if e!=nil{continue}
  modules:=webModuleSource.FindAllStringSubmatch(string(raw),9)
  if len(modules)<1||len(modules)>8{continue}
  p:=webEmbedPlan{}
  found:=map[string]webEmbedMember{}
  bad:=false
  for _,m:=range members{
   if !strings.HasPrefix(m.name,prefix)||m.name==strings.TrimSuffix(prefix,"/"){continue}
   rel:=strings.TrimPrefix(m.name,prefix)
   if rel=="index.html"&&!m.dir||rel=="assets"&&m.dir||strings.HasPrefix(rel,"assets/"){
    if !webEmbedSafeName(rel)||(!m.dir&&rel!="index.html"&&!webAssetExtensions[strings.ToLower(path.Ext(rel))]){
     bad=true;break
    }
    key:=strings.ToLower(rel)
    if _,ok:=found[key];ok{bad=true;break}
    m.name=rel;found[key]=m;p.members=append(p.members,m)
    if !m.dir{p.total+=uint64(m.size)}
   }else if !m.dir{
    // R39 serves only index.html and assets; do not silently drop a
    // potentially required file from an unrecognized web layout.
    bad=true;break
   }
  }
  if bad||p.total==0||p.total>uint64(webEmbedMaxEXE){continue}
  if m,ok:=found["assets"];!ok||!m.dir{continue}
  for _,mod:=range modules{
   name:=mod[1]
   m,ok:=found[strings.ToLower(name)]
   if !webEmbedSafeName(name)||!ok||m.name!=name||m.dir||m.size<=0||m.size>16*1024*1024{bad=true;break}
  }
  if !bad{plans=append(plans,p)}
 }
 return plans,len(plans)>0
}
// A real Go compiler emits a self-contained slice header (pointer to its
// immediately following 48-byte records, length, capacity). Look for the
// exact relationship rather than loose strings or a fixed number of files.
func webFindEmbedded(f io.ReaderAt,size int64)(webEmbedPlan,error){
 regions,e:=webPERegions(f,size);if e!=nil{return webEmbedPlan{},e}
 var plans []webEmbedPlan
 candidates:=0
 goMarker:=false
 buffer:=make([]byte,webEmbedChunk+24)
 for _,region:=range regions{
  for at:=uint64(0);at<region.size;at+=webEmbedChunk{
   n:=region.size-at;if n>uint64(len(buffer)){n=uint64(len(buffer))}
   chunk:=buffer[:int(n)]
   if _,e=f.ReadAt(chunk,region.off+int64(at));e!=nil{return webEmbedPlan{},errors.New("IA_WEB_EXE_NO_LEIBLE")}
   if bytes.Contains(chunk,[]byte("\xff Go buildinf:")){goMarker=true}
   for j:=0;j<webEmbedChunk&&j+24<=len(chunk);j+=8{
    if webU64(chunk[j:j+8])!=region.va+at+uint64(j)+24{continue}
    count:=webU64(chunk[j+8:j+16])
    if count<3||count>webEmbedMaxEntries||count!=webU64(chunk[j+16:j+24]){continue}
    candidates++
    if candidates>512{return webEmbedPlan{},errors.New("IA_WEB_EXE_TABLA_AMBIGUA")}
    members,ok:=webEmbedReadTable(f,regions,region.va+at+uint64(j)+24,count)
    if !ok{continue}
    p,ok:=webEmbedProfile(f,members)
    if ok{plans=append(plans,p...)}
    if len(plans)>1{return webEmbedPlan{},errors.New("IA_WEB_EXE_TABLA_AMBIGUA")}
   }
  }
 }
 if !goMarker||len(plans)!=1{return webEmbedPlan{},errors.New("IA_WEB_EXE_FRONTEND_NO_ENCONTRADO")}
 return plans[0],nil
}
func webEmbeddedHashMatches(sum []byte,want [16]byte)bool{
 // Go 1.23 uses NOTSHA256. A standard SHA256 prefix is also accepted for
 // compatible toolchains; no unchecked/guessed bytes are ever published.
 if len(sum)<16{return false}
 if bytes.Equal(sum[:16],want[:]){return true}
 for i:=0;i<16;i++{if ^sum[i]!=want[i]{return false}}
 return true
}
func webExtractMember(f io.ReaderAt,root string,m webEmbedMember)error{
 if !webEmbedSafeName(m.name){return errors.New("IA_WEB_EXE_RUTA_INSEGURA")}
 to:=filepath.Join(root,filepath.FromSlash(m.name))
 if m.dir{
  return os.MkdirAll(to,0700)
 }
 if e:=os.MkdirAll(filepath.Dir(to),0700);e!=nil{return errors.New("IA_WEB_EXE_EXTRACCION_FALLO")}
 if vxaceCloneCheckAncestors(filepath.Dir(to))!=nil{return errors.New("IA_WEB_EXE_RUTA_INSEGURA")}
 out,e:=os.OpenFile(to,os.O_WRONLY|os.O_CREATE|os.O_EXCL,0600)
 if e!=nil{return errors.New("IA_WEB_EXE_EXTRACCION_FALLO")}
 h:=sha256.New()
 n,copyErr:=io.CopyBuffer(io.MultiWriter(out,h),io.NewSectionReader(f,m.off,m.size),make([]byte,256*1024))
 syncErr:=out.Sync();closeErr:=out.Close()
 if copyErr!=nil||syncErr!=nil||closeErr!=nil||n!=m.size{return errors.New("IA_WEB_EXE_EXTRACCION_FALLO")}
 if !webEmbeddedHashMatches(h.Sum(nil),m.sum){return errors.New("IA_WEB_EXE_RECURSO_SHA_INVALIDO")}
 return nil
}
func webCloneFromEXE(filename,parent string,pkg *packageReader)(string,error){
 exe,e:=filepath.Abs(filename)
 if e!=nil||!strings.EqualFold(filepath.Ext(exe),".exe")||!ordinary(exe)||
    !vxaceCloneOrdinaryPath(exe)||vxaceCloneCheckAncestors(filepath.Dir(exe))!=nil{return "",errors.New("IA_WEB_EXE_RUTA_INVALIDA")}
 if parent==""{parent=filepath.Dir(exe)}
 parent,e=filepath.Abs(parent)
 if e!=nil||vxaceCloneCheckAncestors(parent)!=nil{return "",errors.New("IA_WEB_COPIA_DESTINO_INVALIDO")}
 for _,name:=range webHostFiles{
  if pkg==nil||pkg.files["webhost/"+name]==nil{return "",errors.New("IA_WEB_HOST_NO_INCLUIDO")}
 }
 f,e:=os.Open(exe);if e!=nil{return "",errors.New("IA_WEB_EXE_NO_LEIBLE")}
 defer f.Close()
 before,e:=f.Stat();if e!=nil||!before.Mode().IsRegular(){return "",errors.New("IA_WEB_EXE_NO_LEIBLE")}
 plan,e:=webFindEmbedded(f,before.Size());if e!=nil{return "",e}
 if e=vxaceCheckDiskSpace(parent,2*plan.total+2*1024*1024*1024);e!=nil{return "",e}
 stage,e:=os.MkdirTemp(parent,".ia-web-extract-");if e!=nil{return "",errors.New("IA_WEB_EXE_EXTRACCION_FALLO")}
 // This is a new private scratch directory, never the original game.
 defer os.RemoveAll(stage)
 for _,m:=range plan.members{
  if e=webExtractMember(f,stage,m);e!=nil{return "",e}
 }
 after,e:=os.Lstat(exe)
 if e!=nil||!vxaceSameReplaceFile(before,after){return "",errors.New("IA_WEB_COPIA_ORIGEN_CAMBIADO")}
 if _,e=webValidateFolder(stage);e!=nil{return "",e}
 return webCloneInstall(stage,parent,pkg)
}
