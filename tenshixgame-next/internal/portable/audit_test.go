package portable

import (
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "os"
    "path/filepath"
    "strings"
    "testing"

    "github.com/eduardolupaca01-lgtm/public-translation-regression-lab/tenshixgame-next/internal/translation"
)

func write(t *testing.T,root,relative string,data []byte) {
    t.Helper()
    p:=filepath.Join(root,relative)
    if err:=os.MkdirAll(filepath.Dir(p),0700);err!=nil{t.Fatal(err)}
    if err:=os.WriteFile(p,data,0600);err!=nil{t.Fatal(err)}
}
func jsonBytes(t *testing.T,v any)[]byte {
    t.Helper()
    b,err:=json.Marshal(v);if err!=nil{t.Fatal(err)}
    return b
}
func newFixture(t *testing.T)(root string){
    t.Helper()
    root=filepath.Join(t.TempDir(),"Juego")
    if err:=os.MkdirAll(root,0700);err!=nil{t.Fatal(err)}
    write(t,root,"Game.exe",[]byte("synthetic game"))
    write(t,root,"www/js/plugins.js",[]byte("var $plugins = [{name:'TenshixgameRPGLive',status:true}];"))
    write(t,root,"www/js/plugins/TenshixgameRPGLive.js",[]byte("synthetic fixture"))
    return root
}
func stem(mode string)string{
    hash:=sha256.Sum256([]byte(mode))
    return "game-portable-"+hex.EncodeToString(hash[:])[:24]
}
func marker(t *testing.T,root,workerHash string) {
    t.Helper()
    write(t,root,filepath.Join("Tenshixgame-IA","portable-owner-v1.json"),
        jsonBytes(t,map[string]any{"schema":ownerSchema,"product":product,"worker_sha256":workerHash}))
}
func TestMissingAndForeignSidecarsAreSafeAndNeverModified(t *testing.T){
    root:=newFixture(t)
    initial:=AuditRoot(root)
    if initial.State!="not_installed"||initial.OwnerVerified{t.Fatalf("%+v",initial)}
    write(t,root,"Tenshixgame-IA/private_player_data.dat",[]byte("keep me"))
    foreign:=AuditRoot(root)
    if foreign.State!="unowned" {t.Fatalf("unowned path accepted: %+v",foreign)}
    b,err:=os.ReadFile(filepath.Join(root,"Tenshixgame-IA/private_player_data.dat"))
    if err!=nil||string(b)!="keep me"{t.Fatal("audit modified user data")}
}

func TestExactOriginalNativeSnapshotAndEntryKeysWithBadRecords(t *testing.T){
    root:=newFixture(t)
    marker(t,root,strings.Repeat("0",64))
    data:=filepath.Join("Tenshixgame-IA",".local","TENSHIXGAME-RPG","live-cache")
    source:="「おはよう、夏実。」"
    k,err:=translation.Key(translation.Source{Family:"rpg-maker",Engine:"mv",Language:"ja",Raw:source})
    if err!=nil{t.Fatal(err)}
    base:=stem("auto")
    write(t,root,filepath.Join(data,base+".json"),
        jsonBytes(t,map[string]any{
            "schema":"tx394-live-cache-v1",
            "items":map[string]string{k:"Buenos días, Natsumi.","not_sha":"error"},
            "sources":map[string]string{k:source},
        }))
    write(t,root,filepath.Join(data,base+".live.json"),
        jsonBytes(t,map[string]any{
            "schema":"tx394-live-cache-v1","items":map[string]string{k:"Buenos días, Natsumi."},
            "sources":map[string]string{k:source},
        }))
    write(t,root,filepath.Join(data,base+".live.json.entries",k[:2],k+".json"),
        jsonBytes(t,map[string]any{"schema":"tx394-live-cache-entry-v1",
            "key":k,"source":source,"language":"ja","translated":"Buenos días, Natsumi."}))
    badKey:=strings.Repeat("0",64)
    write(t,root,filepath.Join(data,base+".live.json.entries",badKey[:2],badKey+".json"),
        jsonBytes(t,map[string]any{"schema":"tx394-live-cache-entry-v1",
            "key":badKey,"source":source,"language":"ja","translated":"INCORRECTO"}))
    before,err:=os.ReadFile(filepath.Join(root,data,base+".live.json"))
    if err!=nil{t.Fatal(err)}
    report:=AuditRoot(root)
    if report.State!="owner_marker_valid" || report.WorkerHashMatched {
        t.Fatalf("false genuine model certification %+v",report)
    }
    if report.CacheSnapshots!=2||report.SnapshotRecordsProven!=2||
       report.EntryRecordsProven!=1||report.CacheRecordsRejected<2{
        t.Fatalf("native cached translations not detected correctly: %+v",report)
    }
    after,err:=os.ReadFile(filepath.Join(root,data,base+".live.json"))
    if err!=nil||string(before)!=string(after){t.Fatal("auditor changed cache")}
    if report.OfflineInferenceTested||report.InGameSpanishRenderedTested||report.SecondComputerTested {
        t.Fatal("read-only audit pretended to run live inference")
    }
}

func TestGenuineSizedWorkerHashAndMovedGameRootRemainStable(t *testing.T){
    root:=newFixture(t)
    rel:=filepath.Join("Tenshixgame-IA",".local","TENSHIXGAME-RPG","engine","engine","TenshixgameAI.exe")
    full:=filepath.Join(root,rel)
    if err:=os.MkdirAll(filepath.Dir(full),0700);err!=nil{t.Fatal(err)}
    f,err:=os.Create(full);if err!=nil{t.Fatal(err)}
    if err=f.Truncate(minOriginalWorker+1);err!=nil{t.Fatal(err)}
    if err=f.Close();err!=nil{t.Fatal(err)}
    hash,_,err:=fileHash(root,rel);if err!=nil{t.Fatal(err)}
    marker(t,root,hash)
    report:=AuditRoot(root)
    if report.State!="worker_hash_matches"||!report.WorkerHashMatched {t.Fatalf("%+v",report)}
    relocated:=filepath.Join(filepath.Dir(root),"NuevaUbicacion")
    if err:=os.Rename(root,relocated);err!=nil{t.Fatal(err)}
    again:=AuditRoot(relocated)
    if !again.WorkerHashMatched||again.WorkerBytes!=minOriginalWorker+1 {
        t.Fatalf("copy/rename lost worker identity: %+v",again)
    }
}

func TestRejectsLinkedForeignWorkerWithoutFollowingIt(t *testing.T){
    root:=newFixture(t)
    marker(t,root,strings.Repeat("0",64))
    rel:=filepath.Join("Tenshixgame-IA",".local","TENSHIXGAME-RPG","engine","engine","TenshixgameAI.exe")
    full:=filepath.Join(root,rel)
    if err:=os.MkdirAll(filepath.Dir(full),0700);err!=nil{t.Fatal(err)}
    other:=filepath.Join(t.TempDir(),"not-the-worker.exe")
    if err:=os.WriteFile(other,[]byte("no"),0600);err!=nil{t.Fatal(err)}
    if err:=os.Symlink(other,full);err!=nil{t.Skip("system does not permit symlinks")}
    result:=AuditRoot(root)
    if result.WorkerHashMatched||result.State=="worker_hash_matches" {
        t.Fatal("outside linked file accepted as owned worker")
    }
}

func TestUnfinishedV95StageIsReportedWithoutDeletion(t *testing.T) {
    root:=newFixture(t)
    staged:=filepath.Join(root,".tx771-stage-abandoned")
    if err:=os.Mkdir(staged,0700);err!=nil{t.Fatal(err)}
    write(t,root,".tx771-stage-abandoned/engine-model.keep",[]byte("do not delete"))
    status:=AuditRoot(root)
    if status.State!="not_installed"||status.OrphanInstallStages!=1 {
        t.Fatalf("orphan stage not detected correctly: %+v",status)
    }
    second:=filepath.Join(root,".tx771-onefile-stage-abandoned")
    if err:=os.Mkdir(second,0700);err!=nil{t.Fatal(err)}
    again:=AuditRoot(root)
    if again.OrphanInstallStages!=2 {t.Fatalf("second historical stage prefix not recognized: %+v",again)}
    data,err:=os.ReadFile(filepath.Join(staged,"engine-model.keep"))
    if err!=nil||string(data)!="do not delete" {t.Fatal("read-only audit removed unowned staged content")}
}

func TestPreservedAppVersionsAreOnlyCountedNeverRemoved(t *testing.T){
    root:=newFixture(t)
    marker(t,root,strings.Repeat("0",64))
    write(t,root,"Tenshixgame-IA/App/old-verified/keep.txt",[]byte("older app cache"))
    write(t,root,"Tenshixgame-IA/App/new-verified/keep.txt",[]byte("newer app cache"))
    report:=AuditRoot(root)
    if report.PreservedAppVersions!=2 {t.Fatalf("version count: %+v",report)}
    for _,sub:=range []string{"old-verified","new-verified"} {
        v,e:=os.ReadFile(filepath.Join(root,"Tenshixgame-IA","App",sub,"keep.txt"))
        if e!=nil||len(v)==0{t.Fatal("auditor removed a version of the existing app")}
    }
}

func TestCacheAuditDistinguishesProtectedActorFromJapaneseBody(t *testing.T){
    root:=newFixture(t)
    marker(t,root,strings.Repeat("0",64))
    data:=filepath.Join("Tenshixgame-IA",".local","TENSHIXGAME-RPG","live-cache")
    goodSource:="\\N<隼人 \\N[2]>おはようございます。"
    badSource:="\\N<夏実 \\N[2]>まだ日本語です。"
    sourceType:=func(value string)translation.Source{
        return translation.Source{Family:"rpg-maker",Engine:"mv",Language:"ja",Raw:value}
    }
    goodKey,err:=translation.Key(sourceType(goodSource))
    if err!=nil{t.Fatal(err)}
    badKey,err:=translation.Key(sourceType(badSource))
    if err!=nil{t.Fatal(err)}
    goodResult:="\\N<隼人 \\N[2]>Buenos días."
    badResult:="\\N<夏実 \\N[2]>Todavía 日本語."
    write(t,root,filepath.Join(data,stem("ja")+".live.json"),
        jsonBytes(t,map[string]any{
            "schema":"tx394-live-cache-v1",
            "items":map[string]string{goodKey:goodResult,badKey:badResult},
            "sources":map[string]string{goodKey:goodSource,badKey:badSource},
        }))
    report:=AuditRoot(root)
    if report.SnapshotRecordsProven!=1||report.CacheQualityRejected!=1||
        report.CacheProtectedNameCandidates!=1{
        t.Fatalf("native quality audit mixed protected and visible Japanese %+v",report)
    }
    if report.InGameSpanishRenderedTested||report.OfflineInferenceTested {
        t.Fatal("cache audit claimed actual visible translation")
    }
}

func TestCacheAuditorRejectsMutatedRpgCommandsEvenWithValidSHA(t *testing.T){
    root:=newFixture(t)
    marker(t,root,strings.Repeat("0",64))
    base:=filepath.Join("Tenshixgame-IA",".local","TENSHIXGAME-RPG","live-cache")
    original:="\\N<隼人>\\C[6]おはよう\\C[0] \\V[2]"
    wrong:="\\N<隼人>\\C[6]Hola\\C[0] \\V[9]"
    s:=translation.Source{Family:"rpg-maker",Engine:"mv",Language:"ja",Raw:original}
    key,err:=translation.Key(s)
    if err!=nil{t.Fatal(err)}
    snapshot:=filepath.Join(base,stem("ja")+".live.json")
    write(t,root,snapshot,jsonBytes(t,map[string]any{
        "schema":"tx394-live-cache-v1",
        "items":map[string]string{key:wrong},
        "sources":map[string]string{key:original},
    }))
    entry:=filepath.Join(base,stem("ja")+".live.json.entries",key[:2],key+".json")
    write(t,root,entry,jsonBytes(t,map[string]any{
        "schema":"tx394-live-cache-entry-v1",
        "key":key,"language":"ja","source":original,"translated":wrong,
    }))
    originalBytes,err:=os.ReadFile(filepath.Join(root,snapshot))
    if err!=nil{t.Fatal(err)}
    found:=AuditRoot(root)
    if found.CacheQualityRejected!=2||found.SnapshotRecordsProven!=0||
       found.EntryRecordsProven!=0||found.CacheRecordsRejected!=0{
        t.Fatalf("valid key with unsafe control codes misclassified: %+v",found)
    }
    after,err:=os.ReadFile(filepath.Join(root,snapshot))
    if err!=nil||string(after)!=string(originalBytes){t.Fatal("auditor modified cached text")}
}
