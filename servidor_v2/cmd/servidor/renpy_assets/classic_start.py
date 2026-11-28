# -*- coding: ascii -*-
"""Pre-parser compatibility for the original Ren'Py 4/5 desktop runtime.
Python 2.3 syntax. No engine, archive, or original script is rewritten.
"""
import os
import sys
import codecs

def install_codec_compat():
    if os.name!="nt" or sys.version_info[:2]!=(2,3):
        return False
    import __builtin__
    original=codecs.open
    if getattr(original,"_ia_renpy_legacy",False):
        return True
    def compatible(filename,mode="rb",encoding=None,errors="strict",buffering=1):
        try:
            return original(filename,mode,encoding,errors,buffering)
        except IOError:
            # Python 2.3.3 codecs.open appends b to rU; its file object
            # recognizes only U and rU. Old MSVCRT reports ENOENT for rUb.
            # Retry only this exact read-only UTF-8 script operation on
            # a real existing file. Preserve the native universal newline
            # reader, codec error policy, and permissions.
            if mode not in ("rU","U") or encoding is None or encoding.lower().replace("_","-") not in ("utf-8","utf8"):
                raise
            lower=filename.lower()
            if not (lower.endswith(".rpy") or lower.endswith(".rpym")) or not os.path.isfile(filename):
                raise
            raw=__builtin__.open(filename,"rU",buffering)
            try:
                encoder,decoder,reader,writer=codecs.lookup(encoding)
                result=codecs.StreamReaderWriter(raw,reader,writer,errors)
                result.encoding=encoding
                return result
            except:
                raw.close()
                raise
    compatible._ia_renpy_legacy=True
    codecs.open=compatible
    return True

def native_main(root,game,lint=False,report=None):
    root=os.path.abspath(root).replace("\\","/")
    game=os.path.abspath(game).replace("\\","/")
    lowerroot=os.path.normcase(root)
    lowergame=os.path.normcase(game)
    if lowergame!=lowerroot and not lowergame.startswith(lowerroot+"/"):
        raise ValueError("IA_RENPY_RUTA_CLASICA_INVALIDA")
    if not os.path.isdir(root) or not os.path.isdir(game):
        raise ValueError("IA_RENPY_RUTA_CLASICA_INVALIDA")
    os.chdir(root)
    for path in (root,root+"/module"):
        if os.path.isdir(path) and path not in sys.path:
            sys.path.append(path)
    install_codec_compat()
    if hasattr(sys,"winver") and "SDL_VIDEODRIVER" not in os.environ:
        os.environ["SDL_VIDEODRIVER"]="windib"
    import renpy
    version=str(getattr(renpy,"version",""))
    if not (version.startswith("Ren'Py 4") or version.startswith("Ren'Py 5")):
        raise ValueError("IA_RENPY_CLASICO_VERSION_NO_ADMITIDA")
    if report is not None:
        report("NATIVE_ENGINE "+version)
    if hasattr(renpy,"import_all"):
        renpy.import_all()
    import renpy.main
    main=renpy.main.main
    names=main.func_code.co_varnames[:main.func_code.co_argcount]
    if report is not None:
        report("NATIVE_MAIN_ARGS "+repr(names))
    if not lint:
        import renpy.display.presplash
        renpy.display.presplash.start(game)
    if "lint" in names:
        # Historical 4.x main owns normal restarts and original save path.
        return main(game,lint=lint)
    if names:
        raise ValueError("IA_RENPY_CLASICO_MAIN_NO_ADMITIDO")
    import renpy.game
    import renpy.config
    import optparse
    # The original 5.x executable supplies its own path_to_common and
    # path_to_saves callbacks in __main__. Do not replace them.
    options=optparse.Values(dict(version=False,game=game,savedir=None,lock=None,
        python=None,compile=False,lint=lint,profile=False,leak=False,warp=None))
    while True:
        renpy.game.options=options
        renpy.config.renpy_base=root
        renpy.config.basedir=root
        renpy.config.gamedir=game
        try:
            return renpy.main.main()
        except renpy.game.UtterRestartException:
            renpy.reload_all()

def launch_from_environment():
    root=os.environ["IA_RENPY_CLASSIC_ROOT"]
    game=os.environ["IA_RENPY_CLASSIC_GAME"]
    side=os.path.join(root,"IA Traductora RenPy")
    status=os.path.join(side,"classic-start-status.txt")
    def report(line):
        f=open(status,"ab")
        try:
            f.write(str(line)+"\n")
        finally:
            f.close()
    f=open(status,"wb")
    try:
        f.write("IA_RENPY_CLASICO_INICIO\n")
    finally:
        f.close()
    try:
        native_main(root,game,False,report)
        report("IA_RENPY_CLASICO_FIN")
    except:
        # Local status only; do not include dialogue, file paths or raw errors.
        report("IA_RENPY_CLASICO_INICIO_FALLO")
        raise
