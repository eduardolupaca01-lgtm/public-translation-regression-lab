# IA_SERVIDOR_RENPY_R1_OWNED
init 999 python hide:
    import os as _iasr_os
    import sys as _iasr_sys
    import renpy as _iasr_engine
    _iasr_side = _iasr_os.path.join(_iasr_engine.config.basedir, "IA Traductora RenPy")
    _iasr_diag = _iasr_os.path.join(_iasr_side, "client-startup.txt")
    _iasr_phase = "BOOT"
    try:
        with open(_iasr_diag, "wb") as _iasr_f:
            _iasr_f.write(b"IA_RENPY_BOOT_INICIADO\n")
            _iasr_v = str(getattr(_iasr_engine, "version_only", ""))
            if _iasr_v and len(_iasr_v) < 40 and all(_iasr_c in "0123456789." for _iasr_c in _iasr_v):
                _iasr_f.write(("RENPY_VERSION=" + _iasr_v + "\n").encode("ascii"))
        _iasr_phase = "IMPORTACIONES"
        import json as _iasr_json
        import hashlib as _iasr_hash
        import types as _iasr_types
        _iasr_phase = "VERIFICACION"
        _iasr_source = _iasr_os.path.join(_iasr_side, "client.py")
        with open(_iasr_os.path.join(_iasr_side, "owner-v1.json"), "rb") as _iasr_f:
            _iasr_owner = _iasr_json.loads(_iasr_f.read(65536).decode("utf-8"))
        with open(_iasr_source, "rb") as _iasr_f:
            _iasr_code = _iasr_f.read(262144)
        if _iasr_owner.get("schema") != "ia-servidor-renpy-v1" or _iasr_hash.sha256(_iasr_code).hexdigest() != _iasr_owner.get("client_sha256"):
            raise ValueError("IA_RENPY_CLIENTE_NO_VERIFICADO")
        _iasr_phase = "CARGA_CLIENTE"
        _iasr_mod = _iasr_types.ModuleType("_ia_servidor_renpy_r1")
        _iasr_mod.__file__ = _iasr_source
        _iasr_sys.modules[_iasr_mod.__name__] = _iasr_mod
        eval(compile(_iasr_code, _iasr_source, "exec"), _iasr_mod.__dict__)
        _iasr_phase = "CONEXION_HOOKS"
        _iasr_mod.active_client = _iasr_mod.install(_iasr_engine)
        if _iasr_mod.active_client is None:
            raise ValueError("IA_RENPY_CLIENTE_NO_ACTIVO")
        with open(_iasr_diag, "ab") as _iasr_f:
            _iasr_f.write(b"IA_RENPY_HOOKS_LISTOS\n")
    except Exception as _iasr_e:
        try:
            with open(_iasr_diag, "ab") as _iasr_f:
                _iasr_type = type(_iasr_e).__name__
                if not _iasr_type.isalnum() or len(_iasr_type) > 50:
                    _iasr_type = "Error"
                _iasr_f.write(("IA_RENPY_BOOT_FALLO_" + _iasr_phase + "_" + _iasr_type + "\n").encode("ascii"))
        except Exception:
            pass
        try:
            _iasr_engine.exports.write_log("IA_RENPY_BOOT_FALLO_" + _iasr_phase)
        except Exception:
            pass
