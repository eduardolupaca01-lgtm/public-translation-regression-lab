package main

// Explicit, non-destructive alternative for packed VX Ace copies. Read
// the selected game, create a separate folder and publish only NEW files.
// No source permissions, attributes, registry, files or handles are changed.
import (
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

const vxaceCloneMarker = "IA_COPIA_INCOMPLETA.txt"
const vxaceCloneMaxFiles = 200000
const vxaceCloneMaxBytes = uint64(32)*1024*1024*1024

type vxaceCloneEntry struct {
	rel string
	info os.FileInfo
}

func vxaceCloneCheckAncestors(path string) error {
	absolute,e:=filepath.Abs(path)
	if e!=nil{return errors.New("IA_VXACE_COPIA_RUTA_INVALIDA")}
	for at:=absolute;;at=filepath.Dir(at){
		st,e:=os.Lstat(at)
		if e!=nil||!st.IsDir()||st.Mode()&os.ModeSymlink!=0||!vxaceCloneOrdinaryPath(at){
			return errors.New("IA_VXACE_COPIA_RUTA_INSEGURA")
		}
		if filepath.Dir(at)==at{break}
	}
	return nil
}

// Only a recognized Servidor sidecar is excluded. If it contains a
// journal, recover the original archive from its verified backup, without
// writing to the source. A foreign or altered sidecar is never guessed.
func vxaceCloneOriginal(fp vxaceFingerprint)(string,string,string,error){
	target:=fp.ArchiveFile
	current,e:=digestFile(target)
	if e!=nil{return "","","",errors.New("IA_VXACE_COPIA_ORIGINAL_NO_LEIBLE")}
	sidecar,e:=vxaceFindChild(fp.Root,brandFolder)
	if errors.Is(e,os.ErrNotExist){return target,current,current,nil}
	if e!=nil||vxaceCloneCheckAncestors(sidecar)!=nil{
		return "","","",errors.New("IA_VXACE_COPIA_SIDECAR_NO_VERIFICADO")
	}
	owner,e:=iaReadOwner(filepath.Join(sidecar,"owner-v1.json"))
	if e!=nil||owner.Product!="SERVIDOR-IA-TRADUCTORA"||owner.VXACEHelperSHA==""{
		return "","","",errors.New("IA_VXACE_COPIA_SIDECAR_NO_VERIFICADO")
	}
	install:=filepath.Join(sidecar,"install")
	if vxaceCloneCheckAncestors(install)!=nil{return "","","",errors.New("IA_VXACE_COPIA_SIDECAR_NO_VERIFICADO")}
	receipt,has,e:=vxaceReadReceipt(filepath.Join(install,"vxace-receipt.json"))
	if e!=nil{return "","","",e}
	backup:=filepath.Join(install,"vxace","original-Game.rgss3a")
	if !has{
		if _,e=os.Lstat(backup);errors.Is(e,os.ErrNotExist){return target,current,current,nil}
		if e!=nil||!ordinary(backup)||!vxaceCloneOrdinaryPath(backup)||vxaceCloneCheckAncestors(filepath.Dir(backup))!=nil{
			return "","","",errors.New("IA_VXACE_COPIA_RESPALDO_NO_VERIFICADO")
		}
		d,e:=digestFile(backup)
		if e!=nil||d!=current{return "","","",errors.New("IA_VXACE_COPIA_RESPALDO_NO_VERIFICADO")}
		return target,current,current,nil
	}
	if receipt.Mode!="rgss3a"||receipt.TargetRel!="Game.rgss3a"||
		receipt.PluginSHA!=owner.VXACEPluginSHA||receipt.HelperSHA!=owner.VXACEHelperSHA||receipt.WorkerSHA!=owner.WorkerSHA||
		receipt.Build!=owner.VXACEPluginBuild||
		(receipt.Status!="PREPARED"&&receipt.Status!="INSTALLED"&&receipt.Status!="RESTORED")||
		(current!=receipt.BeforeSHA&&current!=receipt.AfterSHA){
		return "","","",errors.New("IA_VXACE_COPIA_RECIBO_NO_VERIFICADO")
	}
	if (receipt.Status=="INSTALLED"&&current!=receipt.AfterSHA)||(receipt.Status=="RESTORED"&&current!=receipt.BeforeSHA){
		return "","","",errors.New("IA_VXACE_COPIA_RECIBO_NO_VERIFICADO")
	}
	if !ordinary(backup)||!vxaceCloneOrdinaryPath(backup)||vxaceCloneCheckAncestors(filepath.Dir(backup))!=nil{
		return "","","",errors.New("IA_VXACE_COPIA_RESPALDO_NO_VERIFICADO")
	}
	d,e:=digestFile(backup)
	if e!=nil||d!=receipt.BeforeSHA{return "","","",errors.New("IA_VXACE_COPIA_RESPALDO_NO_VERIFICADO")}
	// Even when the source has a completed installation, the new copy
	// is built from its original archive, never by copying the old plugin.
	if current==receipt.BeforeSHA{return target,current,current,nil}
	return backup,d,current,nil
}

func vxaceClonePlan(fp vxaceFingerprint)([]vxaceCloneEntry,uint64,error){
	entries:=[]vxaceCloneEntry{}
	seen:=map[string]bool{}
	var total uint64
	e:=filepath.WalkDir(fp.Root,func(name string,d fs.DirEntry,walkErr error)error{
		if walkErr!=nil{return errors.New("IA_VXACE_COPIA_ENUMERACION_FALLO")}
		if name==fp.Root{return nil}
		rel,e:=filepath.Rel(fp.Root,name)
		if e!=nil||filepath.IsAbs(rel)||rel==".."||strings.HasPrefix(rel,".."+string(filepath.Separator)){
			return errors.New("IA_VXACE_COPIA_RUTA_INSEGURA")
		}
		base:=strings.ToLower(rel)
		if !strings.Contains(rel,string(filepath.Separator)){
			if strings.EqualFold(rel,brandFolder){
				if !d.IsDir()||!vxaceCloneOrdinaryPath(name){return errors.New("IA_VXACE_COPIA_SIDECAR_NO_VERIFICADO")}
				return filepath.SkipDir
			}
			if strings.EqualFold(rel,vxaceCloneMarker){return errors.New("IA_VXACE_COPIA_ORIGEN_INCOMPLETO")}
			// Do not copy an unverified interrupted temporary publication.
			if strings.HasPrefix(base,".ia-vxace-replace-")||strings.HasPrefix(base,".ia-traductora-stage-"){
				return errors.New("IA_VXACE_COPIA_ETAPA_PREVIA_REVISAR")
			}
			if strings.EqualFold(rel,"Game.exe")||strings.EqualFold(rel,vxaceArchiveName){return nil}
		}
		if d.Type()&os.ModeSymlink!=0||!vxaceCloneOrdinaryPath(name)||seen[base]{
			return errors.New("IA_VXACE_COPIA_RUTA_INSEGURA")
		}
		seen[base]=true
		st,e:=d.Info()
		if e!=nil||(!st.IsDir()&&!st.Mode().IsRegular()){
			return errors.New("IA_VXACE_COPIA_RUTA_INSEGURA")
		}
		if !st.IsDir(){
			if st.Size()<0||uint64(st.Size())>vxaceCloneMaxBytes-total{return errors.New("IA_VXACE_COPIA_TAMANO_EXCESIVO")}
			total+=uint64(st.Size())
		}
		if len(entries)>=vxaceCloneMaxFiles{return errors.New("IA_VXACE_COPIA_DEMASIADOS_ARCHIVOS")}
		entries=append(entries,vxaceCloneEntry{rel,st})
		return nil
	})
	return entries,total,e
}

func vxaceCloneFile(src,dst string)error{
	if !vxaceCloneOrdinaryPath(src)||vxaceCloneCheckAncestors(filepath.Dir(src))!=nil||
		vxaceCloneCheckAncestors(filepath.Dir(dst))!=nil{
		return errors.New("IA_VXACE_COPIA_RUTA_INSEGURA")
	}
	return vxaceCopyFileNew(src,dst)
}

func vxaceCloneInstall(gameEXE,parent string,pkg *packageReader)(string,string,error){
	fp,matched,e:=detectVXAce(gameEXE)
	if e!=nil{return "","",e}
	if !matched||!fp.Packed{return "","",errors.New("IA_VXACE_COPIA_SOLO_RGSS3A")}
	if pkg==nil||pkg.files["vxace-helper.exe"]==nil||pkg.files["vxace/IATraductoraVXACE.rb"]==nil{
		return "","",errors.New("IA_VXACE_PAQUETE_INCOMPLETO")
	}
	if vxaceCloneCheckAncestors(fp.Root)!=nil||!vxaceCloneOrdinaryPath(fp.GameEXE)||!vxaceCloneOrdinaryPath(fp.ArchiveFile){
		return "","",errors.New("IA_VXACE_COPIA_RUTA_INSEGURA")
	}
	if parent==""{parent=filepath.Dir(fp.Root)}
	parent,e=filepath.Abs(parent)
	if e!=nil||vxaceCloneCheckAncestors(parent)!=nil{return "","",errors.New("IA_VXACE_COPIA_DESTINO_INVALIDO")}
	// A clone must not be inside the selected game (including an alias).
	rootCanonical,e:=filepath.EvalSymlinks(fp.Root)
	if e!=nil{return "","",errors.New("IA_VXACE_COPIA_RUTA_INSEGURA")}
	parentCanonical,e:=filepath.EvalSymlinks(parent)
	if e!=nil{return "","",errors.New("IA_VXACE_COPIA_DESTINO_INVALIDO")}
	rel,e:=filepath.Rel(strings.ToLower(rootCanonical),strings.ToLower(parentCanonical))
	if e==nil&&rel!=".."&&!strings.HasPrefix(rel,".."+string(filepath.Separator)){
		return "","",errors.New("IA_VXACE_COPIA_DESTINO_DENTRO_DEL_ORIGEN")
	}
	archive,originalSHA,currentSHA,e:=vxaceCloneOriginal(fp)
	if e!=nil{return "","",e}
	archiveStat,e:=os.Stat(archive)
	if e!=nil||archiveStat.Size()<=0||archiveStat.Size()>vxaceMaxArchive{return "","",errors.New("IA_VXACE_COPIA_TAMANO_EXCESIVO")}
	entries,total,e:=vxaceClonePlan(fp)
	if e!=nil{return "","",e}
	// Peak: original backup + helper input + unpacked data + patched output.
	// Package, final executable and bounded script staging are extra.
	needed:=total+4*uint64(archiveStat.Size())+3*1024*1024*1024
	if e=vxaceCheckDiskSpace(parent,needed);e!=nil{return "","",e}

	root,e:=os.MkdirTemp(parent,"Juego-IA-VXACE-")
	if e!=nil{return "","",errors.New("IA_VXACE_COPIA_DESTINO_NO_CREADO")}
	marker:=filepath.Join(root,vxaceCloneMarker)
	if e=createNew(marker,[]byte("Copia incompleta. No ejecutar. El juego de origen no se modifica.\n"));e!=nil{return "","",errors.New("IA_VXACE_COPIA_MARCADOR_FALLO")}
	// Leave a labeled incomplete copy on failure rather than recursively
	// removing files which might have been added by the user.
	for _,entry:=range entries{
		from,to:=filepath.Join(fp.Root,entry.rel),filepath.Join(root,entry.rel)
		st,e:=os.Lstat(from)
		if e!=nil||!vxaceCloneOrdinaryPath(from)||!os.SameFile(st,entry.info){
			return "","",errors.New("IA_VXACE_COPIA_ORIGEN_CAMBIADO")
		}
		if entry.info.IsDir(){
			if !st.IsDir()||vxaceCloneCheckAncestors(from)!=nil||vxaceCloneCheckAncestors(filepath.Dir(to))!=nil{return "","",errors.New("IA_VXACE_COPIA_RUTA_INSEGURA")}
			if e=os.Mkdir(to,0700);e!=nil{return "","",errors.New("IA_VXACE_COPIA_DIRECTORIO_FALLO")}
		}else{
			if !vxaceSameReplaceFile(st,entry.info){return "","",errors.New("IA_VXACE_COPIA_ORIGEN_CAMBIADO")}
			if e=vxaceCloneFile(from,to);e!=nil{return "","",e}
			st,e=os.Lstat(from)
			if e!=nil||!vxaceSameReplaceFile(st,entry.info){return "","",errors.New("IA_VXACE_COPIA_ORIGEN_CAMBIADO")}
		}
	}
	sidecar,e:=iaPrepareAndPublishSidecar(root,pkg)
	if e!=nil{return "","",e}
	if e=iaCheckEngine(sidecar,pkg);e!=nil{return "","",e}
	_,_,helper,plugin,worker,receiptFile,installDir:=vxaceSidecarPaths(root)
	if !vxaceAMD64PE(helper){return "","",errors.New("IA_VXACE_COMPONENTES_NO_INSTALADOS")}
	if e=iaMakeSafeDirs(sidecar,filepath.Join("install","vxace","staging"));e!=nil{return "","",e}
	backup:=filepath.Join(installDir,"original-Game.rgss3a")
	if e=vxaceCloneFile(archive,backup);e!=nil{return "","",e}
	if d,e:=digestFile(backup);e!=nil||d!=originalSHA{return "","",errors.New("IA_VXACE_COPIA_RESPALDO_NO_VERIFICADO")}

	// The native helper receives a minimal isolated input root. The
	// final game directory still has NO Game.exe or Game.rgss3a.
	work,e:=os.MkdirTemp(filepath.Join(installDir,"staging"),".clone-work-")
	if e!=nil{return "","",errors.New("IA_VXACE_STAGING_NO_DISPONIBLE")}
	defer os.RemoveAll(work)
	libRel,e:=filepath.Rel(fp.Root,fp.Library)
	if e!=nil||filepath.IsAbs(libRel)||strings.HasPrefix(libRel,".."){return "","",errors.New("IA_VXACE_COPIA_RUTA_INSEGURA")}
	if e=os.MkdirAll(filepath.Join(work,filepath.Dir(libRel)),0700);e!=nil{return "","",errors.New("IA_VXACE_STAGING_NO_DISPONIBLE")}
	inputEXE:=filepath.Join(work,"Game.exe")
	inputPlugin:=filepath.Join(work,"plugin.rb")
	for _,pair:=range [][2]string{
		{fp.GameEXE,inputEXE},
		{filepath.Join(root,filepath.Base(fp.GameINI)),filepath.Join(work,"Game.ini")},
		{filepath.Join(root,libRel),filepath.Join(work,libRel)},
		{backup,filepath.Join(work,"Game.rgss3a")},
		{plugin,inputPlugin},
	}{
		if e=vxaceCloneFile(pair[0],pair[1]);e!=nil{return "","",e}
	}
	output:=filepath.Join(work,"staging","Game.rgss3a.new")
	if e=os.Mkdir(filepath.Dir(output),0700);e!=nil{return "","",errors.New("IA_VXACE_STAGING_NO_DISPONIBLE")}
	cmd:=exec.Command(helper,"install","--game-root",work,"--plugin",inputPlugin,"--output",output)
	cmd.Dir=work
	raw,runErr:=cmd.CombinedOutput()
	if runErr!=nil{
		code:=strings.TrimSpace(string(raw))
		if !strings.HasPrefix(code,"IA_")||len(code)>110||strings.ContainsAny(code," /\\:\r\n\t"){code="IA_VXACE_HELPER_FALLO"}
		return "","",errors.New(code)
	}
	var report vxaceHelperReport
	helperSHA,e:=digestFile(helper);if e!=nil||helperSHA!=pkg.manifest.Files["vxace-helper.exe"]{return "","",errors.New("IA_VXACE_HELPER_SHA_INVALIDO")}
	pluginSHA,e:=digestFile(plugin);if e!=nil||pluginSHA!=pkg.manifest.Files["vxace/IATraductoraVXACE.rb"]{return "","",errors.New("IA_VXACE_PLUGIN_SHA_INVALIDO")}
	workerSHA,e:=digestFile(worker);if e!=nil||workerSHA!=pkg.manifest.Files["IATraductora.exe"]{return "","",errors.New("IA_VXACE_WORKER_SHA_INVALIDO")}
	if json.Unmarshal(raw,&report)!=nil||report.Schema!="servidor-vxace-install-v1"||report.Mode!="rgss3a"||
		report.OriginalSHA!=originalSHA||report.PluginSHA!=pluginSHA||!report.NonScriptEntriesPreserved||report.ArchiveEntries<=0{
		return "","",errors.New("IA_VXACE_HELPER_REPORTE_INVALIDO")
	}
	st,e:=os.Stat(output)
	if e!=nil||!ordinary(output)||st.Size()<=0||st.Size()>vxaceMaxArchive{return "","",errors.New("IA_VXACE_OUTPUT_TAMANO_INVALIDO")}
	outputSHA,e:=digestFile(output)
	if e!=nil||outputSHA!=report.OutputSHA{return "","",errors.New("IA_VXACE_OUTPUT_SHA_INVALIDO")}
	if d,e:=digestFile(fp.ArchiveFile);e!=nil||d!=currentSHA{return "","",errors.New("IA_VXACE_COPIA_ORIGEN_CAMBIADO")}
	receipt:=vxaceReceipt{Schema:"ia-traductora-vxace-install-v1",BeforeSHA:originalSHA,AfterSHA:outputSHA,
		PluginSHA:pluginSHA,WorkerSHA:workerSHA,HelperSHA:helperSHA,Mode:"rgss3a",TargetRel:"Game.rgss3a",
		Build:vxacePluginBuildID,Status:"PREPARED"}
	journal,_:=json.MarshalIndent(receipt,"","  ")
	if e=createNew(receiptFile,journal);e!=nil{return "","",errors.New("IA_VXACE_RECIBO_NO_GUARDADO")}
	target:=filepath.Join(root,"Game.rgss3a")
	// Create-only publication. Never invokes the archive replacement
	// primitive, including when the source is held open without DELETE.
	if e=vxaceCloneFile(output,target);e!=nil{return "","",e}
	if d,e:=digestFile(target);e!=nil||d!=outputSHA{return "","",errors.New("IA_VXACE_POSTCHECK_SHA_FALLO")}
	receipt.Status="INSTALLED"
	journal,_=json.MarshalIndent(receipt,"","  ")
	if e=writeAtomic(receiptFile,journal);e!=nil{return "","",errors.New("IA_VXACE_RECIBO_PENDIENTE_VERIFICAR")}
	finalEXE:=filepath.Join(root,"Game.exe")
	if e=vxaceCloneFile(inputEXE,finalEXE);e!=nil{return "","",e}
	identity,e:=installedPackageIdentity(finalEXE,pkg)
	if e!=nil{return "","",e}
	if d,e:=digestFile(fp.ArchiveFile);e!=nil||d!=currentSHA{return "","",errors.New("IA_VXACE_COPIA_ORIGEN_CAMBIADO")}
	if e=os.Remove(marker);e!=nil{return "","",errors.New("IA_VXACE_COPIA_MARCADOR_FALLO")}
	return finalEXE,fmt.Sprintf("%s",identity),nil
}
