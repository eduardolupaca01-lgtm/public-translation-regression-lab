"""Tenshixgame RPG — PUBLIC experimental Windows translator, not the private V95 app.

The EXE contains only public code. On its first real translation it downloads
Argos Translate's public ja->en and en->es packages into LOCALAPPDATA.
Supports RPG Maker MV/MZ *offline-file exports*, never injects into a running
game or modifies game files. This is not an assertion of bilingual quality.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import queue
import re
import sys
import tempfile
import threading
from typing import Callable

from translation_lab.cache import DurableTranslationCache
from translation_lab.pipeline import JAPANESE, TranslationRejected, translate_checked

APP_NAME = "Tenshixgame RPG — Prueba pública JA → ES"
PUBLIC_RUNTIME = "argos-translate-1.11.0-ja-en-es-public-pivot"
RPG_FILES = re.compile(r"Map\d{3,4}\.json\Z", re.IGNORECASE)
RPG_OTHER_FILES = {"CommonEvents.json", "Troops.json"}
MAX_JSON_BYTES = 20 * 1024 * 1024


def data_directory() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / ".local" / "share") / "TenshixgameRPGPublicTrial"


def configure_runtime() -> None:
    os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")
    os.environ.setdefault("ARGOS_DEVICE_TYPE", "cpu")
    packages = data_directory() / "public-argos-models"
    packages.mkdir(parents=True, exist_ok=True)
    os.environ["ARGOS_PACKAGES_DIR"] = str(packages)


def load_public_translator(progress: Callable[[str], None] = lambda _: None):
    """Only public Argos models. No private binaries, archives or network API."""
    configure_runtime()
    try:
        import argostranslate.package as packages
        import argostranslate.translate as translation
    except ImportError as exc:
        raise RuntimeError("Falta el motor público Argos Translate del EXE.") from exc

    installed = {(p.from_code, p.to_code) for p in packages.get_installed_packages()}
    required = [("ja", "en"), ("en", "es")]
    missing = [pair for pair in required if pair not in installed]
    if missing:
        progress("Descargando el índice oficial de modelos públicos (requiere Internet)...")
        packages.update_package_index()
        catalog = packages.get_available_packages()
        for source, target in missing:
            match = next((p for p in catalog
                          if p.from_code == source and p.to_code == target), None)
            if match is None:
                raise RuntimeError(f"No existe un modelo público {source}->{target} en el catálogo.")
            progress(f"Descargando e instalando modelo público {source}->{target}...")
            packages.install_from_path(match.download())
    installed = {(p.from_code, p.to_code) for p in packages.get_installed_packages()}
    if not all(pair in installed for pair in required):
        raise RuntimeError("No se instalaron los dos modelos públicos requeridos.")

    progress("Modelos públicos instalados. Traducción neuronal real disponible.")
    return lambda text: translation.translate(text, "ja", "es")


def translate_text(source: str, translator, cache: DurableTranslationCache) -> str:
    if not isinstance(source, str):
        raise TypeError("Se requiere un texto.")
    if not JAPANESE.search(source):
        return source
    return cache.translate_or_get(
        "ja", "es", source, lambda original: translate_checked(original, translator)
    )


def locate_rpg_data(game_folder: Path) -> Path:
    """Only the ordinary JSON data directory of RPG Maker MV or MZ."""
    folder = Path(game_folder).resolve()
    for candidate in (folder / "www" / "data", folder / "data", folder):
        if candidate.is_dir() and any(candidate.glob("Map[0-9][0-9][0-9].json")):
            return candidate
    raise ValueError("No se encontró www/data o data con Map001.json (RPG Maker MV/MZ).")


def json_sources(folder: Path) -> list[Path]:
    files = sorted(
        path for path in folder.iterdir()
        if path.is_file() and not path.is_symlink()
        and (RPG_FILES.fullmatch(path.name) or path.name in RPG_OTHER_FILES)
    )
    if not files:
        raise ValueError("No se encontraron mapas/eventos compatibles.")
    for file in files:
        if file.stat().st_size > MAX_JSON_BYTES:
            raise ValueError(f"Archivo demasiado grande para esta prueba: {file.name}")
    return files


def translate_event_tree(value, translate_one: Callable[[str], str]) -> int:
    """Translate only RPG Maker event dialogue and choice fields.

    Never rewrite IDs, scripts, page conditions, switches, maps, variables,
    references, actor metadata or gameplay logic. Keep JSON keys identical.
    """
    edited = 0
    if isinstance(value, list):
        for item in value:
            edited += translate_event_tree(item, translate_one)
        return edited
    if not isinstance(value, dict):
        return 0
    parameters = value.get("parameters")
    code = value.get("code")
    if type(code) is int and isinstance(parameters, list):
        if code in (401, 405) and parameters and isinstance(parameters[0], str):
            old = parameters[0]
            if JAPANESE.search(old):
                new = translate_one(old)
                if not new or JAPANESE.search(new):
                    raise TranslationRejected("RPG_DIALOGUE_NOT_TRANSLATED")
                parameters[0] = new
                edited += 1
        elif code == 102 and parameters and isinstance(parameters[0], list):
            for index, old in enumerate(parameters[0]):
                if isinstance(old, str) and JAPANESE.search(old):
                    new = translate_one(old)
                    if not new or JAPANESE.search(new):
                        raise TranslationRejected("RPG_CHOICE_NOT_TRANSLATED")
                    parameters[0][index] = new
                    edited += 1
        elif code == 402 and len(parameters) > 1 and isinstance(parameters[1], str):
            old = parameters[1]
            if JAPANESE.search(old):
                new = translate_one(old)
                if not new or JAPANESE.search(new):
                    raise TranslationRejected("RPG_CHOICE_BRANCH_NOT_TRANSLATED")
                parameters[1] = new
                edited += 1
    for key, child in value.items():
        if key != "parameters":
            edited += translate_event_tree(child, translate_one)
    return edited


def export_rpg(game_folder: Path, output_folder: Path, translate_one, progress=None) -> dict:
    """Create a new standalone patch directory, never overwrite the original."""
    progress = progress or (lambda _: None)
    source_root = Path(game_folder).resolve()
    folder = locate_rpg_data(source_root)
    target = Path(output_folder).resolve()
    if target == source_root or source_root in target.parents:
        raise ValueError("La exportación debe estar fuera de la carpeta del juego.")
    if target == folder or folder in target.parents:
        raise ValueError("No se puede escribir dentro de la carpeta original.")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise FileExistsError("Elige una carpeta de destino nueva o vacía.")
    files = json_sources(folder)
    results = []
    for file in files:
        progress(f"Traduciendo {file.name}...")
        document = json.loads(file.read_text(encoding="utf-8-sig"))
        clone = copy.deepcopy(document)
        count = translate_event_tree(clone, translate_one)
        results.append((file.name, clone, count))
    # Fail closed before any files are written when translation fails.
    target.mkdir(parents=True, exist_ok=True)
    modified = []
    for name, data, count in results:
        if count:
            (target / name).write_text(
                json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            modified.append(name)
    report = {
        "kind": "PUBLIC_TRIAL_FILE_EXPORT_NOT_ORIGINAL_PRODUCT",
        "engine": PUBLIC_RUNTIME,
        "source_files_checked": len(files),
        "files_with_translation": len(modified),
        "event_segments_translated": sum(item[2] for item in results),
        "output_files": modified,
        "original_game_modified": False,
        "semantic_human_approval": False,
    }
    (target / "tenshixgame-public-trial-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def run_neural_smoke() -> dict:
    """Actual model inference from the packaged executable, not a mock."""
    translator = load_public_translator()
    folder = data_directory() / "cache"
    with DurableTranslationCache(folder) as cache:
        a = translate_text("ありがとうございます。", translator, cache)
        b = translate_text("学校はどこですか？", translator, cache)
        if not a.strip() or not b.strip() or JAPANESE.search(a + b):
            raise TranslationRejected("PUBLIC_NEURAL_JA_TO_ES_SMOKE_NOT_TRANSLATED")
        saved = cache.get("ja", "es", "ありがとうございます。")
        if saved != a:
            raise RuntimeError("PUBLIC_SQLITE_RESTART_SOURCE_CACHE_MISMATCH")
        with tempfile.TemporaryDirectory(prefix="tenshixgame-rpg-public-") as tmp:
            game = Path(tmp) / "game"
            data = game / "www" / "data"
            data.mkdir(parents=True)
            map_doc = {"events": [None, {"pages": [{"list": [
                {"code": 401, "indent": 0, "parameters": ["ありがとうございます。"]},
                {"code": 102, "indent": 0,
                 "parameters": [["学校はどこですか？", "はい。"], 0, 0, 2, 0]},
                {"code": 111, "indent": 0, "parameters": [1, 2, 0, 17, 0]},
            ]}]}]}
            (data / "Map001.json").write_text(
                json.dumps(map_doc, ensure_ascii=False), encoding="utf-8"
            )
            output = Path(tmp) / "export"
            receipt = export_rpg(
                game, output, lambda text: translate_text(text, translator, cache)
            )
            actual = json.loads((output / "Map001.json").read_text(encoding="utf-8"))
            codes = actual["events"][1]["pages"][0]["list"]
            if receipt["event_segments_translated"] != 3:
                raise RuntimeError("PUBLIC_RPG_DIALOGUE_OR_CHOICES_NOT_TRANSLATED")
            if codes[2] != map_doc["events"][1]["pages"][0]["list"][2]:
                raise RuntimeError("PUBLIC_GAME_LOGIC_MODIFIED")
            if JAPANESE.search(codes[0]["parameters"][0]):
                raise RuntimeError("PUBLIC_GAME_JAPANESE_DIALOGUE_REMAINED")
    return {
        "result": "PASS",
        "engine": PUBLIC_RUNTIME,
        "japanese": ["ありがとうございます。", "学校はどこですか？"],
        "spanish": [a, b],
        "real_model_inference": True,
        "sqlite_cache": "PASS",
        "rpg_maker_mv_mz_synthetic_event_export": "PASS",
        "original_game_modified": False,
        "professional_bilingual_approval": False,
    }


def launch_gui() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry("800x680")
    root.minsize(680, 540)
    queue_out = queue.Queue()
    selected = tk.StringVar(value="No seleccionada")
    status = tk.StringVar(value="Modelos públicos: se descargan en el primer uso.")
    game_path = {"value": None}
    buttons = []
    ttk.Label(root, text="Tenshixgame RPG — prueba pública", font=("Segoe UI", 17, "bold")).pack(
        anchor="w", padx=18, pady=(16, 3)
    )
    ttk.Label(
        root,
        text="Modelo público JA→EN→ES; no es el motor privado anterior. "
             "Exportación local para RPG Maker MV/MZ.",
        wraplength=750,
    ).pack(anchor="w", padx=18)
    ttk.Label(root, text="Texto original en japonés:").pack(anchor="w", padx=18, pady=(15, 3))
    source_box = tk.Text(root, height=5, wrap="word")
    source_box.pack(fill="both", expand=True, padx=18)
    source_box.insert("1.0", "ありがとうございます。")
    ttk.Label(root, text="Resultado en español:").pack(anchor="w", padx=18, pady=(12, 3))
    target_box = tk.Text(root, height=6, wrap="word")
    target_box.pack(fill="both", expand=True, padx=18)

    def process_messages():
        try:
            while True:
                kind, value = queue_out.get_nowait()
                if kind == "status":
                    status.set(value)
                elif kind == "translated":
                    target_box.delete("1.0", tk.END)
                    target_box.insert(tk.END, value)
                elif kind == "error":
                    status.set("Error: " + value)
                    messagebox.showerror("No se pudo traducir", value)
                elif kind == "finish":
                    for button in buttons:
                        button.configure(state="normal")
        except queue.Empty:
            pass
        root.after(100, process_messages)

    def worker(operation):
        for button in buttons:
            button.configure(state="disabled")
        def execute():
            try:
                operation(lambda s: queue_out.put(("status", s)))
            except Exception as exc:
                queue_out.put(("error", str(exc)))
            finally:
                queue_out.put(("finish", None))
        threading.Thread(target=execute, daemon=True).start()

    def translate_clicked():
        text = source_box.get("1.0", "end-1c")
        if not text.strip():
            messagebox.showwarning("Texto vacío", "Escribe texto japonés.")
            return
        def operation(progress):
            t = load_public_translator(progress)
            with DurableTranslationCache(data_directory() / "cache") as cache:
                translated = translate_text(text, t, cache)
            queue_out.put(("translated", translated))
            progress("Texto traducido con un modelo público. Comprueba la fidelidad.")
        worker(operation)

    def select_game():
        folder = filedialog.askdirectory(title="Seleccionar juego RPG Maker MV/MZ")
        if folder:
            game_path["value"] = Path(folder)
            selected.set(folder)

    def export_clicked():
        source = game_path["value"]
        if not source:
            messagebox.showinfo("Seleccionar juego", "Primero selecciona la carpeta del juego.")
            return
        dest_parent = filedialog.askdirectory(title="Elegir carpeta para guardar una COPIA")
        if not dest_parent:
            return
        destination = Path(dest_parent) / "Tenshixgame-RPG-ES419-prueba"
        def operation(progress):
            t = load_public_translator(progress)
            with DurableTranslationCache(data_directory() / "cache") as cache:
                summary = export_rpg(
                    source, destination,
                    lambda text: translate_text(text, t, cache),
                    progress=progress,
                )
            progress(
                f"Exportado: {summary['event_segments_translated']} segmentos en "
                f"{summary['files_with_translation']} archivos. Carpeta: {destination}"
            )
        worker(operation)

    bar = ttk.Frame(root)
    bar.pack(fill="x", padx=18, pady=12)
    translate_button = ttk.Button(bar, text="Traducir japonés", command=translate_clicked)
    translate_button.pack(side="left", padx=(0, 8))
    buttons.append(translate_button)
    choose_button = ttk.Button(bar, text="Elegir juego MV/MZ", command=select_game)
    choose_button.pack(side="left", padx=8)
    export_button = ttk.Button(bar, text="Exportar diálogos a una COPIA", command=export_clicked)
    export_button.pack(side="left", padx=8)
    buttons.append(export_button)
    ttk.Label(root, textvariable=selected, wraplength=740).pack(anchor="w", padx=18)
    ttk.Label(root, textvariable=status, wraplength=740).pack(
        anchor="w", padx=18, pady=(14, 7)
    )
    ttk.Label(
        root, text="Prueba experimental: exige revisión humana. No modifica la carpeta "
                   "original ni instala complementos ni se conecta a un juego en ejecución.",
        wraplength=740,
    ).pack(anchor="w", padx=18, pady=(0, 15))
    root.after(100, process_messages)
    root.mainloop()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--smoke-test", action="store_true",
                        help="Descarga modelos públicos y realiza inferencia real.")
    parser.add_argument("--receipt-out", type=Path,
                        help="Guarda resultado JSON verificable, incluso si falla.")
    args = parser.parse_args(argv)
    if args.version:
        if sys.stdout:
            print(APP_NAME + " | " + PUBLIC_RUNTIME)
        return 0
    if not args.smoke_test:
        launch_gui()
        return 0
    try:
        result = run_neural_smoke()
        status = 0
    except Exception as exc:
        result = {"result": "FAIL", "error": str(exc), "engine": PUBLIC_RUNTIME,
                  "real_model_inference": False}
        status = 1
    if args.receipt_out:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if sys.stdout:
        print(json.dumps(result, ensure_ascii=False))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
