# IA_SERVIDOR_RENPY_R1_OWNED
init 999 python hide:
    try:
        import os as _iasr_os
        import sys as _iasr_sys
        import json as _iasr_json
        import hashlib as _iasr_hash
        import types as _iasr_types
        import renpy as _iasr_engine
        _iasr_side = _iasr_os.path.join(config.basedir, "IA Traductora RenPy")
        _iasr_source = _iasr_os.path.join(_iasr_side, "client.py")
        with open(_iasr_os.path.join(_iasr_side, "owner-v1.json"), "rb") as _iasr_f:
            _iasr_owner = _iasr_json.loads(_iasr_f.read(65536).decode("utf-8"))
        with open(_iasr_source, "rb") as _iasr_f:
            _iasr_code = _iasr_f.read(262144)
        if _iasr_owner.get("schema") != "ia-servidor-renpy-v1" or _iasr_hash.sha256(_iasr_code).hexdigest() != _iasr_owner.get("client_sha256"):
            raise ValueError("IA_RENPY_CLIENTE_NO_VERIFICADO")
        _iasr_mod = _iasr_types.ModuleType("_ia_servidor_renpy_r1")
        _iasr_mod.__file__ = _iasr_source
        _iasr_sys.modules[_iasr_mod.__name__] = _iasr_mod
        eval(compile(_iasr_code, _iasr_source, "exec"), _iasr_mod.__dict__)
        _iasr_mod.install(_iasr_engine)
    except Exception:
        try:
            renpy.log("IA_RENPY_ARRANQUE_NO_DISPONIBLE")
        except Exception:
            pass
