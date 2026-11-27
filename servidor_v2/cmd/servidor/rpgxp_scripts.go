package main

// RPG Maker XP uses raw Ruby 1.8 Marshal strings. This deliberately narrow
// parser accepts only an array of [Fixnum, byte string, zlib byte string].
// It never invokes Marshal.load or evaluates game scripts. Object references,
// Ruby 1.9 encoding wrappers and unexpected shapes fail closed.
import (
    "bytes"
    "compress/zlib"
    "encoding/binary"
    "encoding/json"
    "errors"
    "io"
    "os"
    "path/filepath"
    "strings"
)
const (
    xpScriptName = "IA Traductora RGSS1"
    xpScriptMarker = "# IA_TRADUCTORA_RPGXP_RGSS1_OWNER_V1"
    xpMaxArchive = 64*1024*1024
    xpMaxSections = 8192
    xpMaxInflated = 8*1024*1024
    xpMaxTotalInflated = 128*1024*1024
)
var xpInvalidMarshal = errors.New("IA_RPGXP_SCRIPTS_MARSHAL_INVALIDO")
type xpScriptRow struct {
    id int64
    name []byte
    packed []byte
    raw []byte
}
type xpReader struct { data []byte; pos int }
func (r *xpReader) take(n int) ([]byte,error) {
    if n<0 || n>len(r.data)-r.pos {return nil,xpInvalidMarshal}
    b:=r.data[r.pos:r.pos+n];r.pos+=n;return b,nil
}
func (r *xpReader) tag(expected byte) error {
    b,e:=r.take(1);if e!=nil||b[0]!=expected{return xpInvalidMarshal};return nil
}
func (r *xpReader) number() (int64,error) {
    b,e:=r.take(1);if e!=nil{return 0,e}
    c:=int(int8(b[0]))
    switch {
    case c==0:return 0,nil
    case c>4:return int64(c-5),nil
    case c< -4:return int64(c+5),nil
    }
    n:=c;if n<0{n=-n}
    raw,e:=r.take(n);if e!=nil{return 0,e}
    var v int64
    if c<0{v=-1}
    for j,x:=range raw{
        shift:=uint(j*8)
        v=(v & ^(int64(255)<<shift)) | int64(x)<<shift
    }
    return v,nil
}
func (r *xpReader) string(max int) ([]byte,error) {
    if e:=r.tag('"');e!=nil{return nil,e}
    n,e:=r.number();if e!=nil||n<0||n>int64(max){return nil,xpInvalidMarshal}
    return r.take(int(n))
}
func xpNumber(n int64) []byte {
    if n==0{return []byte{0}}
    if n>0&&n<123{return []byte{byte(n+5)}}
    if n<0&&n>=-123{return []byte{byte(int8(n-5))}}
    var data [4]byte
    binary.LittleEndian.PutUint32(data[:],uint32(n))
    count:=4
    if n>=0 {for count>1&&data[count-1]==0{count--};return append([]byte{byte(count)},data[:count]...)}
    for count>1&&data[count-1]==255{count--}
    return append([]byte{byte(int8(-count))},data[:count]...)
}
func xpString(b []byte) []byte {
    out:=append([]byte{'"'},xpNumber(int64(len(b)))...)
    return append(out,b...)
}
func xpInflate(packed []byte, limit int64) ([]byte,error) {
    if len(packed)==0||limit<0{return nil,xpInvalidMarshal}
    reader:=bytes.NewReader(packed)
    z,e:=zlib.NewReader(reader);if e!=nil{return nil,xpInvalidMarshal}
    b,e:=io.ReadAll(io.LimitReader(z,limit+1))
    closed:=z.Close()
    if e!=nil||closed!=nil||int64(len(b))>limit||reader.Len()!=0{return nil,xpInvalidMarshal}
    return b,nil
}
func xpParseScripts(raw []byte) ([]xpScriptRow,error) {
    if len(raw)<4||len(raw)>xpMaxArchive||!bytes.Equal(raw[:2],[]byte{4,8}){return nil,xpInvalidMarshal}
    r:=xpReader{raw,2}
    if e:=r.tag('[');e!=nil{return nil,e}
    count,e:=r.number();if e!=nil||count<1||count>xpMaxSections{return nil,xpInvalidMarshal}
    rows:=make([]xpScriptRow,0,int(count))
    total:=int64(0)
    for i:=int64(0);i<count;i++{
        start:=r.pos
        if e:=r.tag('[');e!=nil{return nil,e}
        n,e:=r.number();if e!=nil||n!=3{return nil,xpInvalidMarshal}
        if e:=r.tag('i');e!=nil{return nil,e}
        id,e:=r.number();if e!=nil||id < -(1<<30)||id>=(1<<30){return nil,xpInvalidMarshal}
        name,e:=r.string(1024);if e!=nil||bytes.IndexByte(name,0)>=0{return nil,xpInvalidMarshal}
        packed,e:=r.string(xpMaxArchive);if e!=nil{return nil,e}
        limit:=int64(xpMaxInflated)
        if left:=int64(xpMaxTotalInflated)-total;left<limit{limit=left}
        plain,e:=xpInflate(packed,limit);if e!=nil{return nil,e}
        total+=int64(len(plain))
        rows=append(rows,xpScriptRow{id,name,packed,raw[start:r.pos]})
    }
    if r.pos!=len(raw){return nil,xpInvalidMarshal}
    return rows,nil
}
func xpCompress(code []byte)([]byte,error){
    var out bytes.Buffer
    z:=zlib.NewWriter(&out)
    if _,e:=z.Write(code);e!=nil{z.Close();return nil,e}
    if e:=z.Close();e!=nil{return nil,e}
    return out.Bytes(),nil
}
func xpEncodeRow(id int64,name,packed []byte) []byte {
    out:=append([]byte{'['},xpNumber(3)...)
    out=append(out,'i');out=append(out,xpNumber(id)...)
    out=append(out,xpString(name)...);return append(out,xpString(packed)...)
}
func xpEncodeRows(rows [][]byte) ([]byte,error){
    size:=3+len(xpNumber(int64(len(rows))))
    for _,row:=range rows{if len(row)>xpMaxArchive-size{return nil,xpInvalidMarshal};size+=len(row)}
    out:=make([]byte,0,size)
    out=append(out,4,8,'[');out=append(out,xpNumber(int64(len(rows)))...)
    for _,row:=range rows{out=append(out,row...)}
    return out,nil
}
// Insert immediately before the only Main section. Original row bytes
// (IDs, raw encoded names and compressed code) are copied verbatim.
func xpPatchScripts(original,plugin []byte)([]byte,error){
    if len(plugin)==0||len(plugin)>1024*1024||!bytes.HasPrefix(plugin,[]byte(xpScriptMarker+"\n"))||
        bytes.IndexByte(plugin,0)>=0{return nil,errors.New("IA_RPGXP_PLUGIN_NO_VERIFICADO")}
    rows,e:=xpParseScripts(original);if e!=nil{return nil,e}
    if len(rows)>=xpMaxSections{return nil,xpInvalidMarshal}
    main:=-1
    used:=map[int64]bool{}
    for i,row:=range rows{
        used[row.id]=true
        if strings.EqualFold(string(row.name),xpScriptName){return nil,errors.New("IA_RPGXP_PLUGIN_PREEXISTENTE")}
        if strings.EqualFold(string(row.name),"Main"){
            if main>=0{return nil,errors.New("IA_RPGXP_MAIN_AMBIGUO")};main=i
        }
    }
    if main<0{return nil,errors.New("IA_RPGXP_MAIN_NO_ENCONTRADO")}
    var id int64=1
    for used[id]{id++}
    compressed,e:=xpCompress(plugin);if e!=nil{return nil,e}
    inserted:=xpEncodeRow(id,[]byte(xpScriptName),compressed)
    parts:=make([][]byte,0,len(rows)+1)
    for i,row:=range rows{
        if i==main{parts=append(parts,inserted)}
        parts=append(parts,row.raw)
    }
    updated,e:=xpEncodeRows(parts);if e!=nil{return nil,e}
    check,e:=xpParseScripts(updated);if e!=nil||len(check)!=len(rows)+1{return nil,xpInvalidMarshal}
    for i,row:=range rows{
        j:=i;if i>=main{j++}
        if !bytes.Equal(row.raw,check[j].raw){return nil,errors.New("IA_RPGXP_SCRIPTS_POSTCHECK_FALLO")}
    }
    code,e:=xpInflate(check[main].packed,int64(len(plugin)))
    if e!=nil||!bytes.Equal(code,plugin)||string(check[main].name)!=xpScriptName{return nil,errors.New("IA_RPGXP_PLUGIN_POSTCHECK_FALLO")}
    return updated,nil
}
type xpStageReceipt struct {
    Schema string `json:"schema"`
    Before string `json:"before_sha256"`
    After string `json:"after_sha256"`
    Plugin string `json:"plugin_sha256"`
}
// A lab stage is a fresh directory outside the selected game. It creates a
// byte-exact backup and a candidate; it cannot activate the candidate.
func xpStageScripts(gameEXE,stageParent string,plugin []byte)(string,error){
    matched,e:=detectRPGXP(gameEXE)
    if !matched||e!=nil{return "",errors.New(rpgxpInvalidCode)}
    root,e:=filepath.Abs(filepath.Dir(gameEXE));if e!=nil{return "",e}
    parent,e:=filepath.Abs(stageParent);if e!=nil{return "",e}
    if e=vxaceNoSymlinkAncestors(parent);e!=nil{return "",e}
    rel,e:=filepath.Rel(root,parent)
    if e!=nil||rel=="."||(!filepath.IsAbs(rel)&&rel!=".."&&!strings.HasPrefix(rel,".."+string(filepath.Separator))){
        return "",errors.New("IA_RPGXP_STAGING_DENTRO_DEL_JUEGO")
    }
    data,e:=vxaceDirectoryChild(root,"Data");if e!=nil{return "",e}
    scripts,e:=vxaceOrdinaryChild(data,"Scripts.rxdata",xpMaxArchive);if e!=nil{return "",e}
    f,e:=os.Open(scripts);if e!=nil{return "",e}
    original,e:=io.ReadAll(io.LimitReader(f,xpMaxArchive+1));f.Close()
    if e!=nil||len(original)>xpMaxArchive{return "",xpInvalidMarshal}
    updated,e:=xpPatchScripts(original,plugin);if e!=nil{return "",e}
    originalSHA:=hash(original)
    if _,e=vxaceVerifiedReplaceFile(scripts,originalSHA);e!=nil{return "",e}
    stage,e:=os.MkdirTemp(parent,"rpgxp-stage-");if e!=nil{return "",e}
    ok:=false
    defer func(){if !ok{_ = os.RemoveAll(stage)}}()
    receipt:=xpStageReceipt{"ia-rpgxp-stage-v1",originalSHA,hash(updated),hash(plugin)}
    manifest,e:=json.Marshal(receipt);if e!=nil{return "",e}
    for _,v:=range []struct{name string; bytes []byte}{{"Scripts.original.rxdata",original},{"Scripts.candidate.rxdata",updated},{"receipt.json",manifest}}{
        if e=createNew(filepath.Join(stage,v.name),v.bytes);e!=nil{return "",e}
    }
    for _,pair:=range []struct{name,want string}{{"Scripts.original.rxdata",receipt.Before},{"Scripts.candidate.rxdata",receipt.After}}{
        got,e:=digestFile(filepath.Join(stage,pair.name));if e!=nil||got!=pair.want{return "",errors.New("IA_RPGXP_STAGE_SHA_FALLO")}
    }
    if _,e=vxaceVerifiedReplaceFile(scripts,originalSHA);e!=nil{return "",e}
    ok=true;return stage,nil
}
