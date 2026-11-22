package portable

// Read-only inspection of the EXACT original TX771+ owned game-local runtime.
// NEVER calls worker executable, mutates the game, restores old binaries, or
// assumes that a successful hash means the game renders Spanish text.
import (
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "errors"
    "io"
    "os"
    "path/filepath"
    "regexp"
    "strings"

    "github.com/eduardolupaca01-lgtm/public-translation-regression-lab/tenshixgame-next/internal/translation"
)

const ownerSchema="tenshixgame-rpg-portable-owner-v1"
const product="TENSHIXGAME-RPG"
const minOriginalWorker int64=100*1024*1024
var hex64=regexp.MustCompile("^[a-f0-9]{64}$")

type Report struct {
    State string
    OwnerVerified bool
    WorkerHashMatched bool
    WorkerBytes int64
    PluginPresent bool
    ManifestPresent bool
    CacheSnapshots int
    SnapshotRecordsProven int
    SnapshotRecordsUnverifiable int
    EntryRecordsProven int
    CacheRecordsRejected int
    CacheFilesSkipped int
    Issues []string
    // This read-only structural audit NEVER asserts gameplay certification.
    OfflineInferenceTested bool
    InGameSpanishRenderedTested bool
    SecondComputerTested bool
}

func isWithin(root,p string)bool {
    rel,e:=filepath.Rel(root,p)
    return e==nil&&rel!=".."&&!filepath.IsAbs(rel)&&!strings.HasPrefix(rel,".."+string(filepath.Separator))
}
func plainDir(root,relative string)bool {
    p:=filepath.Join(root,relative)
    if !isWithin(root,p){return false}
    st,e:=os.Lstat(p)
    if e!=nil||!st.IsDir()||st.Mode()&os.ModeSymlink!=0{return false}
    rp,e:=filepath.EvalSymlinks(p)
    if e!=nil{return false}
    rr,e:=filepath.EvalSymlinks(root)
    return e==nil&&isWithin(rr,rp)
}
func plainFile(root,relative string,cap int64)bool {
    p:=filepath.Join(root,relative)
    if !isWithin(root,p){return false}
    st,e:=os.Lstat(p)
    if e!=nil||!st.Mode().IsRegular()||st.Mode()&os.ModeSymlink!=0{return false}
    if cap>0 && st.Size()>cap{return false}
    rp,e:=filepath.EvalSymlinks(p)
    if e!=nil{return false}
    rr,e:=filepath.EvalSymlinks(root)
    return e==nil&&isWithin(rr,rp)
}
func fileHash(root,relative string)(string,int64,error) {
    if !plainFile(root,relative,0){return "",0,errors.New("archivo enlazado o ausente")}
    p:=filepath.Join(root,relative)
    f,e:=os.Open(p);if e!=nil{return "",0,e}
    defer f.Close()
    st,e:=f.Stat();if e!=nil{return "",0,e}
    h:=sha256.New()
    _,e=io.CopyBuffer(h,f,make([]byte,1<<20))
    if e!=nil{return "",0,e}
    return hex.EncodeToString(h.Sum(nil)),st.Size(),nil
}
func readJSON(root,rel string,limit int64,v any)error {
    if !plainFile(root,rel,limit){return errors.New("archivo inseguro o excedido")}
    raw,e:=os.ReadFile(filepath.Join(root,rel))
    if e!=nil{return e}
    return json.Unmarshal(raw,v)
}
func cacheFolder(base string)string{
    return filepath.Join(base,".local","TENSHIXGAME-RPG","live-cache")
}

type cacheSnapshot struct {
    Schema string `json:"schema"`
    Items map[string]string `json:"items"`
    Sources map[string]string `json:"sources"`
}
type cacheEntry struct {
    Schema string `json:"schema"`
    Key string `json:"key"`
    Source string `json:"source"`
    Language string `json:"language"`
    Translated string `json:"translated"`
}

// AuditRoot intentionally publishes counts and diagnostic codes only, not the
// source dialogue, translated text, game folder, secrets, or session tokens.
func AuditRoot(gameRoot string)Report {
    result:=Report{State:"invalid",Issues:[]string{}}
    root,e:=filepath.Abs(gameRoot)
    if e!=nil {result.Issues=append(result.Issues,"GAME_ROOT_INVALID");return result}
    st,e:=os.Lstat(root)
    if e!=nil||!st.IsDir()||st.Mode()&os.ModeSymlink!=0{
        result.Issues=append(result.Issues,"GAME_ROOT_NOT_ORDINARY");return result
    }
    sideRel:="Tenshixgame-IA"
    if _,e:=os.Lstat(filepath.Join(root,sideRel));os.IsNotExist(e){
        result.State="not_installed"
        result.Issues=append(result.Issues,"NO_GAME_LOCAL_RUNTIME")
        return result
    }
    if !plainDir(root,sideRel){
        result.Issues=append(result.Issues,"UNSAFE_OR_FOREIGN_RUNTIME_FOLDER");return result
    }
    var marker struct{
        Schema string `json:"schema"`
        Product string `json:"product"`
        WorkerSHA256 string `json:"worker_sha256"`
    }
    if e:=readJSON(root,filepath.Join(sideRel,"portable-owner-v1.json"),2048,&marker);e!=nil||
        marker.Schema!=ownerSchema||marker.Product!=product||!hex64.MatchString(marker.WorkerSHA256){
        result.State="unowned"
        result.Issues=append(result.Issues,"UNVERIFIED_OWNER_MARKER")
        return result
    }
    result.OwnerVerified=true
    result.State="owner_marker_valid"
    base:=filepath.Join(sideRel,".local","TENSHIXGAME-RPG")
    worker:=filepath.Join(base,"engine","engine","TenshixgameAI.exe")
    if plainFile(root,worker,0){
        hash,size,hashErr:=fileHash(root,worker)
        result.WorkerBytes=size
        if hashErr==nil&&size>=minOriginalWorker&&hash==marker.WorkerSHA256{
            result.WorkerHashMatched=true
        }
    }
    if !result.WorkerHashMatched{
        result.Issues=append(result.Issues,"V95_WORKER_MISSING_TOO_SMALL_OR_HASH_MISMATCH")
    }
    // Bundle models require the ORIGINAL host VerifyInstalledIntegrity; this
    // presence signal is NOT a substitute for that verification.
    result.ManifestPresent=plainFile(root,filepath.Join(base,"engine","engine","bundle_manifest.json"),4<<20)
    if !result.ManifestPresent{result.Issues=append(result.Issues,"V95_MODEL_MANIFEST_NOT_CONFIRMED")}
    for _,layout:=range []string{"www/js","js"} {
        if plainFile(root,filepath.Join(layout,"plugins.js"),4<<20)&&
           plainFile(root,filepath.Join(layout,"plugins","TenshixgameRPGLive.js"),4<<20){
            result.PluginPresent=true
        }
    }
    if !result.PluginPresent{result.Issues=append(result.Issues,"RPG_NATIVE_PLUGIN_NOT_FOUND")}
    cacheRel:=cacheFolder(sideRel)
    if plainDir(root,cacheRel){
        for _,mode:=range []string{"auto","ja","en"} {
            sum:=sha256.Sum256([]byte(mode))
            stem:="game-portable-"+hex.EncodeToString(sum[:])[:24]+".json"
            for _,suffix:=range []string{".json",".live.json"}{
                name:=strings.TrimSuffix(stem,".json")+suffix
                if !plainFile(root,filepath.Join(cacheRel,name),5<<20){continue}
                result.CacheSnapshots++
                var snapshot cacheSnapshot
                if err:=readJSON(root,filepath.Join(cacheRel,name),5<<20,&snapshot);
                   err!=nil||snapshot.Schema!="tx394-live-cache-v1" {
                    result.CacheRecordsRejected++;continue
                }
                if len(snapshot.Items)>12000{
                    result.CacheRecordsRejected++;continue
                }
                for k,value:=range snapshot.Items {
                    if !hex64.MatchString(k)||strings.TrimSpace(value)==""{
                        result.CacheRecordsRejected++;continue
                    }
                    original,exists:=snapshot.Sources[k]
                    if !exists {
                        result.SnapshotRecordsUnverifiable++;continue
                    }
                    language:=mode
                    if mode=="auto"{language=translation.ResolveAutoLanguage(original)}
                    native,err:=translation.Key(translation.Source{
                        Family:"rpg-maker",Engine:"mv",Language:language,Raw:original,
                    })
                    if err!=nil||native!=k {
                        result.CacheRecordsRejected++;continue
                    }
                    result.SnapshotRecordsProven++
                }
            }
        }
        // Exact TX757 per-entry store: <snapshot>.live.json.entries/xx/key.json
        // Bound file counts and sizes; reject symlinks and never print text.
        const maxEntries=12000
        for _,mode:=range []string{"auto","ja","en"} {
            sum:=sha256.Sum256([]byte(mode))
            stem:="game-portable-"+hex.EncodeToString(sum[:])[:24]+".live.json.entries"
            dir:=filepath.Join(cacheRel,stem)
            if !plainDir(root,dir){continue}
            buckets,e:=os.ReadDir(filepath.Join(root,dir))
            if e!=nil{continue}
            for _,bucket:=range buckets {
                if len(bucket.Name())!=2||!plainDir(root,filepath.Join(dir,bucket.Name())){result.CacheFilesSkipped++;continue}
                entries,e:=os.ReadDir(filepath.Join(root,dir,bucket.Name()))
                if e!=nil{result.CacheFilesSkipped++;continue}
                for _,entry:=range entries {
                    if result.EntryRecordsProven+result.CacheRecordsRejected>=maxEntries {
                        result.CacheFilesSkipped++;continue
                    }
                    name:=entry.Name()
                    if !strings.HasSuffix(name,".json") {continue}
                    key:=strings.TrimSuffix(name,".json")
                    rel:=filepath.Join(dir,bucket.Name(),name)
                    if !hex64.MatchString(key)||!strings.HasPrefix(key,bucket.Name()) {
                        result.CacheRecordsRejected++;continue
                    }
                    var record cacheEntry
                    if e:=readJSON(root,rel,32768,&record);e!=nil||
                        record.Schema!="tx394-live-cache-entry-v1"||record.Key!=key||
                        strings.TrimSpace(record.Translated)=="" {
                        result.CacheRecordsRejected++;continue
                    }
                    native,e:=translation.Key(translation.Source{Family:"rpg-maker",Engine:"mv",Language:record.Language,Raw:record.Source})
                    if e!=nil||native!=record.Key {
                        result.CacheRecordsRejected++;continue
                    }
                    result.EntryRecordsProven++
                }
            }
        }
    }else{
        result.Issues=append(result.Issues,"NO_GAME_LOCAL_CACHE_DIRECTORY")
    }
    if result.OwnerVerified&&result.WorkerHashMatched{
        result.State="worker_hash_matches"
    }
    // Never assert that the translation is visible or the package is fully
    // tested on another PC. Those require real user-game acceptance.
    return result
}
