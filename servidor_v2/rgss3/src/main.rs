mod install;

use encoding_rs::SHIFT_JIS;
use rpgmad_lib::{decrypt_from_reader, encrypt_to_vec, ArchiveEntry, Engine};
use rvpacker_txt_rs_lib::{EngineType, FileFlags, Mode, Processor};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::panic::{catch_unwind, AssertUnwindSafe};
use tempfile::tempdir;

const REPORT_SCHEMA: &str = "tenshixgame-rgss3-inventory-v1";
const MAX_ARCHIVE: u64 = 1024 * 1024 * 1024;
const MAX_ENTRY: u64 = 256 * 1024 * 1024;
const MAX_TOTAL_DATA: u64 = 1024 * 1024 * 1024;
const MAX_ENTRIES: usize = 100_000;

#[derive(Serialize)]
struct Report {
    schema: &'static str,
    engine: &'static str,
    game_name: String,
    layout: &'static str,
    archive_sha256: Option<String>,
    archive_entries: usize,
    data_files: usize,
    data_bytes: u64,
    scripts_present: bool,
    system_present: bool,
    inventory_status: &'static str,
    text_files: usize,
    text_entries: usize,
    untranslated_entries: usize,
    errors: Vec<String>,
}

fn ordinary(path: &Path) -> bool {
    fs::symlink_metadata(path)
        .map(|m| m.file_type().is_file() && !m.file_type().is_symlink())
        .unwrap_or(false)
}

fn checked_root(path: &Path) -> Result<PathBuf, String> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|_| "IA_RGSS3_CWD_INVALIDO".to_string())?
            .join(path)
    };
    let canonical = absolute
        .canonicalize()
        .map_err(|_| "IA_RGSS3_ROOT_NO_ACCESIBLE".to_string())?;
    let mut cursor = canonical.as_path();
    loop {
        let meta = fs::symlink_metadata(cursor)
            .map_err(|_| "IA_RGSS3_RUTA_NO_VERIFICABLE".to_string())?;
        if meta.file_type().is_symlink() {
            return Err("IA_RGSS3_ENLACE_SIMBOLICO_NO_ADMITIDO".into());
        }
        if let Some(parent) = cursor.parent() {
            if parent == cursor {
                break;
            }
            cursor = parent;
        } else {
            break;
        }
    }
    if !canonical.is_dir() {
        return Err("IA_RGSS3_ROOT_NO_ES_DIRECTORIO".into());
    }
    Ok(canonical)
}

fn sha256(path: &Path) -> Result<String, String> {
    let mut file = File::open(path).map_err(|_| "IA_RGSS3_ARCHIVO_NO_LEIBLE".to_string())?;
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 1024 * 1024];
    loop {
        let n = file
            .read(&mut buffer)
            .map_err(|_| "IA_RGSS3_HASH_LECTURA_FALLIDA".to_string())?;
        if n == 0 {
            break;
        }
        hash.update(&buffer[..n]);
    }
    Ok(format!("{:x}", hash.finalize()))
}

fn decode_archive_path(raw: &[u8]) -> Result<PathBuf, String> {
    let (decoded, _, had_errors) = SHIFT_JIS.decode(raw);
    if had_errors {
        return Err("IA_RGSS3_RUTA_SHIFT_JIS_INVALIDA".into());
    }
    let normalized = decoded.replace('\\', "/");
    if normalized.is_empty()
        || normalized.starts_with('/')
        || normalized.contains(':')
        || normalized.contains('\0')
        || normalized.contains('\n')
        || normalized.contains('\r')
    {
        return Err("IA_RGSS3_RUTA_ARCHIVO_NO_SEGURA".into());
    }
    let mut result = PathBuf::new();
    for part in normalized.split('/') {
        if part.is_empty() || part == "." || part == ".." {
            return Err("IA_RGSS3_RUTA_ARCHIVO_NO_SEGURA".into());
        }
        result.push(part);
    }
    if result.components().any(|c| !matches!(c, Component::Normal(_))) {
        return Err("IA_RGSS3_RUTA_ARCHIVO_NO_SEGURA".into());
    }
    Ok(result)
}

fn is_data_path(path: &Path) -> bool {
    path.components()
        .next()
        .map(|c| c.as_os_str().to_string_lossy().eq_ignore_ascii_case("Data"))
        .unwrap_or(false)
}

fn extract_data_only(archive_path: &Path, destination: &Path) -> Result<(usize, usize, u64), String> {
    let meta = fs::metadata(archive_path)
        .map_err(|_| "IA_RGSS3_ARCHIVE_NO_LEIBLE".to_string())?;
    if meta.len() < 8 || meta.len() > MAX_ARCHIVE {
        return Err("IA_RGSS3_ARCHIVE_TAMANO_NO_ADMITIDO".into());
    }
    let mut header = [0u8; 8];
    File::open(archive_path)
        .and_then(|mut f| f.read_exact(&mut header))
        .map_err(|_| "IA_RGSS3_ARCHIVE_CABECERA_NO_LEIBLE".to_string())?;
    if &header[..7] != b"RGSSAD\0" || header[7] != 3 {
        return Err("IA_RGSS3_ARCHIVE_NO_ES_RGSS3A".into());
    }

    let file = File::open(archive_path)
        .map_err(|_| "IA_RGSS3_ARCHIVE_NO_LEIBLE".to_string())?;
    let mut archive = decrypt_from_reader(file)
        .map_err(|_| "IA_RGSS3_ARCHIVE_CORRUPTO_O_NO_COMPATIBLE".to_string())?;
    let count = archive.entry_count();
    if count == 0 || count > MAX_ENTRIES {
        return Err("IA_RGSS3_CANTIDAD_ENTRADAS_NO_ADMITIDA".into());
    }

    let mut names = HashSet::new();
    let mut data_files = 0usize;
    let mut data_bytes = 0u64;
    let mut total = 0u64;

    for index in 0..count {
        let raw_path = archive.path(index).to_vec();
        let relative = decode_archive_path(&raw_path)?;
        let key = relative.to_string_lossy().replace('\\', "/").to_lowercase();
        if !names.insert(key) {
            return Err("IA_RGSS3_RUTA_DUPLICADA".into());
        }

        if !is_data_path(&relative) {
            continue;
        }

        let mut reader = archive
            .read_entry(index)
            .map_err(|_| "IA_RGSS3_ENTRADA_NO_LEIBLE".to_string())?;
        let mut bytes = Vec::new();
        reader
            .by_ref()
            .take(MAX_ENTRY + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| "IA_RGSS3_ENTRADA_LECTURA_FALLIDA".to_string())?;
        if bytes.len() as u64 > MAX_ENTRY {
            return Err("IA_RGSS3_ENTRADA_EXCESIVA".into());
        }
        total = total.saturating_add(bytes.len() as u64);
        if total > MAX_TOTAL_DATA {
            return Err("IA_RGSS3_DATA_EXPANSION_EXCESIVA".into());
        }

        let output = destination.join(&relative);
        let parent = output
            .parent()
            .ok_or_else(|| "IA_RGSS3_DESTINO_DATA_INVALIDO".to_string())?;
        fs::create_dir_all(parent)
            .map_err(|_| "IA_RGSS3_TEMP_NO_SE_PUEDE_CREAR".to_string())?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)
            .map_err(|_| "IA_RGSS3_TEMP_NO_SE_PUEDE_ESCRIBIR".to_string())?;
        file.write_all(&bytes)
            .map_err(|_| "IA_RGSS3_TEMP_ESCRITURA_FALLIDA".to_string())?;
        file.sync_all()
            .map_err(|_| "IA_RGSS3_TEMP_SYNC_FALLIDO".to_string())?;
        data_files += 1;
        data_bytes += bytes.len() as u64;
    }

    Ok((count, data_files, data_bytes))
}

fn inventory_text(data_dir: &Path) -> Result<(usize, usize, usize), String> {
    let output = tempdir().map_err(|_| "IA_RGSS3_TEMP_NO_DISPONIBLE".to_string())?;
    let mut processor = Processor {
        mode: Mode::read(),
        file_flags: FileFlags::all(),
        ..Default::default()
    };
    let processed = catch_unwind(AssertUnwindSafe(|| {
        processor.process(EngineType::VXAce, data_dir, output.path(), None)
    }));
    match processed {
        Err(_) => return Err("IA_RGSS3_MARSHAL_PARSER_PANIC".into()),
        Ok(Err(_)) => return Err("IA_RGSS3_MARSHAL_NO_ADMITIDO".into()),
        Ok(Ok(())) => {}
    }

    let mut files = 0usize;
    let mut entries = 0usize;
    let mut untranslated = 0usize;
    let mut stack = vec![output.path().to_path_buf()];
    while let Some(folder) = stack.pop() {
        for entry in fs::read_dir(folder)
            .map_err(|_| "IA_RGSS3_INVENTARIO_LECTURA_FALLIDA".to_string())?
        {
            let entry = entry.map_err(|_| "IA_RGSS3_INVENTARIO_ENTRADA_FALLIDA".to_string())?;
            let path = entry.path();
            let kind = entry
                .file_type()
                .map_err(|_| "IA_RGSS3_INVENTARIO_TIPO_FALLIDO".to_string())?;
            if kind.is_symlink() {
                return Err("IA_RGSS3_INVENTARIO_ENLACE_SIMBOLICO".into());
            }
            if kind.is_dir() {
                stack.push(path);
                continue;
            }
            if path.extension().and_then(|x| x.to_str()) != Some("txt") {
                continue;
            }
            let text = fs::read_to_string(&path)
                .map_err(|_| "IA_RGSS3_INVENTARIO_TEXTO_INVALIDO".to_string())?;
            files += 1;
            for line in text.lines() {
                if line.starts_with("<!>") {
                    continue;
                }
                if let Some((source, target)) = line.split_once("<#>") {
                    if !source.trim().is_empty() {
                        entries += 1;
                        if target.trim().is_empty() {
                            untranslated += 1;
                        }
                    }
                }
            }
        }
    }
    Ok((files, entries, untranslated))
}

fn inspect(game: &Path) -> Result<Report, String> {
    let root = checked_root(game)?;
    if !ordinary(&root.join("Game.exe")) || !ordinary(&root.join("Game.ini")) {
        return Err("IA_RGSS3_GAME_EXE_INI_FALTANTE".into());
    }

    let archive_path = root.join("Game.rgss3a");
    let data_dir = root.join("Data");
    let archive_exists = ordinary(&archive_path);
    let loose_data_exists = ordinary(&data_dir.join("System.rvdata2"))
        || ordinary(&data_dir.join("Scripts.rvdata2"));
    if archive_exists && loose_data_exists {
        return Err("IA_RGSS3_LAYOUT_PACKED_LOOSE_AMBIGUO".into());
    }
    if !archive_exists && !loose_data_exists {
        return Err("IA_RGSS3_ARCHIVE_O_DATA_FALTANTE".into());
    }

    let mut report = Report {
        schema: REPORT_SCHEMA,
        engine: "RPG Maker VX Ace / RGSS3",
        game_name: root.file_name().unwrap_or_default().to_string_lossy().into_owned(),
        layout: if archive_exists { "RGSS3A_PACKED" } else { "DATA_LOOSE" },
        archive_sha256: None,
        archive_entries: 0,
        data_files: 0,
        data_bytes: 0,
        scripts_present: false,
        system_present: false,
        inventory_status: "NOT_RUN",
        text_files: 0,
        text_entries: 0,
        untranslated_entries: 0,
        errors: Vec::new(),
    };

    let staging = tempdir().map_err(|_| "IA_RGSS3_TEMP_NO_DISPONIBLE".to_string())?;
    let data_root = if archive_exists {
        report.archive_sha256 = Some(sha256(&archive_path)?);
        let extracted = staging.path().join("unpacked");
        fs::create_dir_all(&extracted)
            .map_err(|_| "IA_RGSS3_TEMP_NO_DISPONIBLE".to_string())?;
        let (entries, data_files, data_bytes) = extract_data_only(&archive_path, &extracted)?;
        report.archive_entries = entries;
        report.data_files = data_files;
        report.data_bytes = data_bytes;
        extracted.join("Data")
    } else {
        report.data_files = fs::read_dir(&data_dir)
            .map_err(|_| "IA_RGSS3_DATA_NO_LEIBLE".to_string())?
            .filter_map(Result::ok)
            .filter(|e| ordinary(&e.path()))
            .count();
        data_dir
    };

    report.scripts_present = ordinary(&data_root.join("Scripts.rvdata2"));
    report.system_present = ordinary(&data_root.join("System.rvdata2"));
    if !report.scripts_present || !report.system_present {
        report.inventory_status = "INCOMPLETE";
        report.errors.push("IA_RGSS3_SCRIPTS_O_SYSTEM_FALTANTE".into());
        return Ok(report);
    }

    match inventory_text(&data_root) {
        Ok((files, entries, untranslated)) => {
            report.inventory_status = "OK";
            report.text_files = files;
            report.text_entries = entries;
            report.untranslated_entries = untranslated;
        }
        Err(code) => {
            report.inventory_status = "REJECTED";
            report.errors.push(code);
        }
    }
    Ok(report)
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("Uso: tenshixgame-rgss3-probe inspect <juego> | install <juego> <plugin.rb> | restore <juego>");
        std::process::exit(2);
    }
    let result = match args[1].as_str() {
        "inspect" => inspect(Path::new(&args[2])).and_then(|report| {
            let json = serde_json::to_string_pretty(&report)
                .map_err(|_| "IA_RGSS3_REPORT_SERIALIZE_FAILED".to_string())?;
            println!("{}", json);
            if report.inventory_status == "REJECTED" {
                return Err("IA_RGSS3_INVENTORY_REJECTED".into());
            }
            Ok(())
        }),
        "install" if args.len() >= 4 => install::install(Path::new(&args[2]), Path::new(&args[3]))
            .and_then(|receipt| {
                println!("{}", serde_json::to_string_pretty(&receipt)
                    .map_err(|_| "IA_RGSS3_RECEIPT_SERIALIZE_FAILED".to_string())?);
                Ok(())
            }),
        "restore" => install::restore(Path::new(&args[2])).and_then(|receipt| {
            println!("{}", serde_json::to_string_pretty(&receipt)
                .map_err(|_| "IA_RGSS3_RECEIPT_SERIALIZE_FAILED".to_string())?);
            Ok(())
        }),
        _ => Err("IA_RGSS3_COMMAND_INVALID".into()),
    };
    if let Err(code) = result {
        eprintln!("{}", code);
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn archive_path_rejects_traversal_and_absolute_paths() {
        assert!(decode_archive_path(b"Data\\Map001.rvdata2").is_ok());
        assert!(decode_archive_path(b"..\\outside.txt").is_err());
        assert!(decode_archive_path(b"C:\\outside.txt").is_err());
        assert!(decode_archive_path(b"\\absolute.txt").is_err());
    }

    #[test]
    fn vxace_archive_roundtrip_keeps_every_entry() {
        let entries = [
            ArchiveEntry { path: b"Data\\System.rvdata2", data: b"system-fixture" },
            ArchiveEntry { path: b"Data\\Scripts.rvdata2", data: b"scripts-fixture" },
            ArchiveEntry { path: b"Graphics\\Tilesets\\Tileset1.png", data: b"png-fixture" },
            ArchiveEntry { path: b"Audio\\BGM\\theme.ogg", data: b"audio-fixture" },
        ];
        let encrypted = encrypt_to_vec(&entries, Engine::Vxace).expect("encrypt fixture");
        assert_eq!(&encrypted[..8], b"RGSSAD\0\x03");
        let mut archive = decrypt_from_reader(Cursor::new(encrypted)).expect("decrypt fixture");
        assert_eq!(archive.entry_count(), entries.len());
        let mut seen = Vec::new();
        for index in 0..archive.entry_count() {
            let path = archive.path(index).to_vec();
            let mut content = Vec::new();
            archive.read_entry(index).expect("entry reader").read_to_end(&mut content).expect("entry read");
            seen.push((path, content));
        }
        assert_eq!(seen.len(), 4);
        assert!(seen.iter().any(|(p, b)| p.ends_with(b"Scripts.rvdata2") && b == b"scripts-fixture"));
        assert!(seen.iter().any(|(p, b)| p.ends_with(b"theme.ogg") && b == b"audio-fixture"));
    }
}
