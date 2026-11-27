use encoding_rs::SHIFT_JIS;
use marshal_rs::{dump, load};
use rpgmad_lib::{
    decrypt_from_reader, encrypt_to_writer, ArchiveEntry, Engine, EntrySource,
};
use rvpacker_txt_rs_lib::{core::Base, types::Scripts};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{
    collections::HashSet,
    env,
    fs::{self, File, OpenOptions},
    io::{self, BufReader, BufWriter, Read, Write},
    path::{Path, PathBuf},
};
use tempfile::Builder as TempDirBuilder;

const MAX_PLUGIN_BYTES: u64 = 1024 * 1024;
const MAX_SCRIPT_BYTES: u64 = 512 * 1024 * 1024;
const MAX_ENTRY_BYTES: u64 = 512 * 1024 * 1024;
const MAX_TOTAL_BYTES: u64 = 4 * 1024 * 1024 * 1024;
const MAX_ARCHIVE_BYTES: u64 = 900 * 1024 * 1024;
const MAX_ENTRIES: usize = 200_000;
const PLUGIN_NAME: &str = "IA Traductora RGSS3";
const PLUGIN_MARKER: &str = "# IA_TRADUCTORA_VXACE_RGSS3_OWNER_V1";

#[derive(Debug)]
struct GameLayout {
    root: PathBuf,
    archive: Option<PathBuf>,
    scripts: Option<PathBuf>,
}

#[derive(Debug, Clone)]
struct EntryRecord {
    raw_path: Vec<u8>,
    decoded_path: String,
    file: PathBuf,
    size: usize,
    sha256: String,
}

#[derive(Clone)]
struct DiskEntry {
    raw_path: Vec<u8>,
    file: PathBuf,
    size: usize,
}

impl EntrySource for DiskEntry {
    fn path(&self) -> &[u8] {
        &self.raw_path
    }

    fn size(&self) -> usize {
        self.size
    }

    fn open(&self) -> io::Result<impl Read> {
        File::open(&self.file)
    }
}

fn fail(code: &str) -> String {
    code.to_owned()
}

fn ordinary(path: &Path, max: u64) -> bool {
    match fs::symlink_metadata(path) {
        Ok(meta) => meta.is_file() && !meta.file_type().is_symlink() && meta.len() > 0 && meta.len() <= max,
        Err(_) => false,
    }
}

fn sha256_file(path: &Path) -> Result<String, String> {
    let mut file = File::open(path).map_err(|_| fail("IA_VXACE_ARCHIVO_NO_LEIBLE"))?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];
    loop {
        let count = file.read(&mut buffer).map_err(|_| fail("IA_VXACE_LECTURA_FALLO"))?;
        if count == 0 {
            break;
        }
        hasher.update(&buffer[..count]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

fn read_bounded(path: &Path, max: u64) -> Result<Vec<u8>, String> {
    if !ordinary(path, max) {
        return Err(fail("IA_VXACE_ARCHIVO_NO_ORDINARIO"));
    }
    let mut file = File::open(path).map_err(|_| fail("IA_VXACE_ARCHIVO_NO_LEIBLE"))?;
    let mut output = Vec::new();
    file.take(max + 1)
        .read_to_end(&mut output)
        .map_err(|_| fail("IA_VXACE_LECTURA_FALLO"))?;
    if output.is_empty() || output.len() as u64 > max {
        return Err(fail("IA_VXACE_TAMANO_INVALIDO"));
    }
    Ok(output)
}

fn ini_values(path: &Path) -> Result<(String, String), String> {
    let bytes = read_bounded(path, 64 * 1024)?;
    // Game.ini titles may be ANSI/Shift-JIS. The fields used here are ASCII;
    // decode lossily so unrelated localized titles cannot reject a valid game.
    let text = String::from_utf8_lossy(&bytes);
    let mut in_game = false;
    let mut library = None;
    let mut scripts = None;
    for raw in text.lines() {
        let line = raw.trim().trim_start_matches('\u{feff}');
        if line.is_empty() || line.starts_with(';') || line.starts_with('#') {
            continue;
        }
        if line.starts_with('[') && line.ends_with(']') {
            in_game = line[1..line.len() - 1].trim().eq_ignore_ascii_case("Game");
            continue;
        }
        if !in_game {
            continue;
        }
        let Some((key, value)) = line.split_once('=') else {
            return Err(fail("IA_VXACE_GAME_INI_INVALIDO"));
        };
        let value = value.trim().to_owned();
        if key.trim().eq_ignore_ascii_case("Library") {
            if library.replace(value).is_some() {
                return Err(fail("IA_VXACE_GAME_INI_DUPLICADO"));
            }
        } else if key.trim().eq_ignore_ascii_case("Scripts") {
            if scripts.replace(value).is_some() {
                return Err(fail("IA_VXACE_GAME_INI_DUPLICADO"));
            }
        }
    }
    let library = library.ok_or_else(|| fail("IA_VXACE_GAME_INI_INVALIDO"))?;
    let scripts = scripts.unwrap_or_else(|| "Data\\Scripts.rvdata2".to_owned());
    let normalized_scripts = scripts.replace('\\', "/").trim_start_matches("./").to_ascii_lowercase();
    if normalized_scripts != "data/scripts.rvdata2" {
        return Err(fail("IA_VXACE_SCRIPTS_PATH_NO_ADMITIDO"));
    }
    if Path::new(&library.replace('\\', "/"))
        .file_name()
        .and_then(|name| name.to_str())
        .map(|name| name.eq_ignore_ascii_case("RGSS301.dll"))
        != Some(true)
    {
        return Err(fail("IA_VXACE_GAME_INI_INVALIDO"));
    }
    let normalized = scripts.replace('\\', "/").trim_start_matches("./").to_ascii_lowercase();
    if normalized != "data/scripts.rvdata2" {
        return Err(fail("IA_VXACE_SCRIPTS_PATH_NO_ADMITIDO"));
    }
    Ok((library, scripts))
}

fn validate_game_root(root: &Path) -> Result<GameLayout, String> {
    let root = root.canonicalize().map_err(|_| fail("IA_VXACE_JUEGO_NO_VALIDO"))?;
    if !root.is_dir() || root.symlink_metadata().map(|m| m.file_type().is_symlink()).unwrap_or(true) {
        return Err(fail("IA_VXACE_JUEGO_NO_VALIDO"));
    }
    for required in ["Game.exe", "RGSS301.dll", "Game.ini"] {
        if !ordinary(&root.join(required), 64 * 1024 * 1024) {
            return Err(fail("IA_VXACE_RUNTIME_NO_VERIFICADO"));
        }
    }
    let _ = ini_values(&root.join("Game.ini"))?;
    let archive = root.join("Game.rgss3a");
    if archive.is_symlink() {
        return Err(fail("IA_VXACE_RGSS3A_INVALIDO"));
    }
    if archive.exists() {
        if !ordinary(&archive, MAX_ARCHIVE_BYTES) {
            return Err(fail("IA_VXACE_RGSS3A_INVALIDO"));
        }
        let mut header = [0u8; 8];
        File::open(&archive)
            .and_then(|mut file| file.read_exact(&mut header))
            .map_err(|_| fail("IA_VXACE_RGSS3A_INVALIDO"))?;
        if header != *b"RGSSAD\0\x03" {
            return Err(fail("IA_VXACE_RGSS3A_INVALIDO"));
        }
        return Ok(GameLayout {
            root,
            archive: Some(archive),
            scripts: None,
        });
    }
    let data = root.join("Data");
    if data.symlink_metadata().map(|m| !m.is_dir() || m.file_type().is_symlink()).unwrap_or(true) {
        return Err(fail("IA_VXACE_DATA_NO_DISPONIBLE"));
    }
    let scripts = data.join("Scripts.rvdata2");
    for name in ["Scripts.rvdata2", "System.rvdata2", "MapInfos.rvdata2"] {
        let file = data.join(name);
        let limit = if name == "Scripts.rvdata2" { MAX_SCRIPT_BYTES } else { 128 * 1024 * 1024 };
        let header = read_bounded(&file, limit)?;
        if header.len() < 2 || header[..2] != [4, 8] {
            return Err(fail("IA_VXACE_MARSHAL_INVALIDO"));
        }
    }
    Ok(GameLayout {
        root,
        archive: None,
        scripts: Some(scripts),
    })
}

fn patch_scripts(original: &[u8], plugin: &str) -> Result<(Vec<u8>, usize), String> {
    if original.len() as u64 > MAX_SCRIPT_BYTES || original.get(..2) != Some(&[4, 8]) {
        return Err(fail("IA_VXACE_MARSHAL_INVALIDO"));
    }
    if plugin.len() as u64 > MAX_PLUGIN_BYTES || !plugin.contains(PLUGIN_MARKER) {
        return Err(fail("IA_VXACE_PLUGIN_NO_VERIFICADO"));
    }
    let arena = load(original).map_err(|_| fail("IA_VXACE_MARSHAL_INVALIDO"))?;
    let root = arena.root();
    let mut scripts: Scripts =
        Base::decode_scripts(&arena, root, None).map_err(|_| fail("IA_VXACE_SCRIPTS_DECODE_FALLO"))?;
    if scripts.numbers.len() != scripts.names.len() || scripts.names.len() != scripts.contents.len() {
        return Err(fail("IA_VXACE_SCRIPTS_ESTRUCTURA_INVALIDA"));
    }
    let mut owned: Vec<usize> = scripts
        .names
        .iter()
        .enumerate()
        .filter_map(|(index, name)| if name == PLUGIN_NAME { Some(index) } else { None })
        .collect();
    if owned.len() > 1 {
        return Err(fail("IA_VXACE_PLUGIN_DUPLICADO"));
    }
    let index = if let Some(index) = owned.pop() {
        if !scripts.contents[index].contains(PLUGIN_MARKER) {
            return Err(fail("IA_VXACE_PLUGIN_AJENO"));
        }
        if scripts.contents[index] != plugin { return Err(fail("IA_VXACE_PLUGIN_PREEXISTENTE_DISTINTO")); }
        return Ok((original.to_vec(), index));
    } else {
        let main_index = scripts
            .names
            .iter()
            .position(|name| name.eq_ignore_ascii_case("Main"))
            .ok_or_else(|| fail("IA_VXACE_MAIN_SCRIPT_NO_ENCONTRADO"))?;
        let next = scripts
            .numbers
            .iter()
            .copied()
            .max()
            .unwrap_or(0)
            .checked_add(1)
            .ok_or_else(|| fail("IA_VXACE_SCRIPT_ID_AGOTADO"))?;
        scripts.numbers.insert(main_index, next);
        scripts.names.insert(main_index, PLUGIN_NAME.to_owned());
        scripts.contents.insert(main_index, plugin.to_owned());
        main_index
    };
    let encoded = dump(&Base::encode_scripts(&scripts));
    if encoded.len() as u64 > MAX_SCRIPT_BYTES || encoded.get(..2) != Some(&[4, 8]) {
        return Err(fail("IA_VXACE_MARSHAL_WRITE_INVALIDO"));
    }
    let check = load(&encoded).map_err(|_| fail("IA_VXACE_MARSHAL_WRITE_INVALIDO"))?;
    let check_scripts: Scripts =
        Base::decode_scripts(&check, check.root(), None).map_err(|_| fail("IA_VXACE_MARSHAL_WRITE_INVALIDO"))?;
    if check_scripts.numbers != scripts.numbers || check_scripts.names != scripts.names
        || check_scripts.contents != scripts.contents
        || check_scripts.names.get(index).map(String::as_str) != Some(PLUGIN_NAME)
        || check_scripts.contents.get(index).map(String::as_str) != Some(plugin)
    {
        return Err(fail("IA_VXACE_PLUGIN_POSTCHECK_FALLO"));
    }
    Ok((encoded, index))
}

fn safe_archive_path(raw: &[u8], index: usize) -> Result<(String, Vec<String>), String> {
    let (decoded, _, had_errors) = SHIFT_JIS.decode(raw);
    if had_errors {
        return Err(format!("IA_VXACE_PATH_ENCODING_{index}"));
    }
    let decoded = decoded.into_owned();
    let entry = ArchiveEntry {
        path: decoded.as_bytes(),
        data: &[],
    };
    let components = entry
        .path_components()
        .ok_or_else(|| format!("IA_VXACE_PATH_UNSAFE_{index}"))?;
    let mut parts = Vec::new();
    for part in components {
        let value = String::from_utf8(part.to_vec()).map_err(|_| format!("IA_VXACE_PATH_ENCODING_{index}"))?;
        if value.is_empty() || value == "." || value == ".." || value.contains(':') || value.contains('\0') {
            return Err(format!("IA_VXACE_PATH_UNSAFE_{index}"));
        }
        parts.push(value);
    }
    if parts.is_empty() {
        return Err(format!("IA_VXACE_PATH_UNSAFE_{index}"));
    }
    Ok((decoded, parts))
}

fn file_sha256(path: &Path) -> Result<String, String> {
    sha256_file(path)
}

fn extract_archive(
    archive_path: &Path,
    staging: &Path,
) -> Result<Vec<EntryRecord>, String> {
    let archive_bytes = fs::metadata(archive_path)
        .map_err(|_| fail("IA_VXACE_ARCHIVE_STAT_FALLO"))?
        .len();
    if archive_bytes > MAX_ARCHIVE_BYTES {
        return Err(fail("IA_VXACE_ARCHIVE_TOO_LARGE"));
    }
    let mut archive = decrypt_from_reader(
        File::open(archive_path).map_err(|_| fail("IA_VXACE_ARCHIVE_OPEN_FALLO"))?,
    )
    .map_err(|_| fail("IA_VXACE_RGSS3A_CORRUPTO"))?;
    let count = archive.entry_count();
    if count == 0 || count > MAX_ENTRIES {
        return Err(fail("IA_VXACE_ARCHIVE_ENTRY_COUNT_INVALID"));
    }
    let unpacked = staging.join("unpacked");
    fs::create_dir(&unpacked).map_err(|_| fail("IA_VXACE_STAGING_FALLO"))?;
    let mut seen = HashSet::with_capacity(count);
    let mut records = Vec::with_capacity(count);
    let mut total = 0u64;
    for index in 0..count {
        let raw_path = archive.path(index).to_vec();
        let (decoded_path, _parts) = safe_archive_path(&raw_path, index)?;
        let duplicate = decoded_path.replace('\\', "/").to_lowercase();
        if !seen.insert(duplicate) {
            return Err(fail("IA_VXACE_ARCHIVE_DUPLICATE_PATH"));
        }
        // Never materialize an archive-controlled path on the host filesystem.
        let target = unpacked.join(format!("entry-{index:08}.bin"));
        let mut output = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&target)
            .map_err(|_| fail("IA_VXACE_STAGING_FALLO"))?;
        let reader = archive
            .read_entry(index)
            .map_err(|_| fail("IA_VXACE_ARCHIVE_READ_FALLO"))?;
        let allowance = MAX_ENTRY_BYTES.min(MAX_TOTAL_BYTES.saturating_sub(total));
        let copied = io::copy(&mut reader.take(allowance + 1), &mut output).map_err(|_| fail("IA_VXACE_ARCHIVE_READ_FALLO"))?;
        if copied > allowance { return Err(fail("IA_VXACE_ARCHIVE_TOTAL_TOO_LARGE")); }
        if copied > MAX_ENTRY_BYTES {
            return Err(fail("IA_VXACE_ARCHIVE_ENTRY_TOO_LARGE"));
        }
        total = total.checked_add(copied).ok_or_else(|| fail("IA_VXACE_ARCHIVE_TOTAL_TOO_LARGE"))?;
        if total > MAX_TOTAL_BYTES {
            return Err(fail("IA_VXACE_ARCHIVE_TOTAL_TOO_LARGE"));
        }
        output.sync_all().map_err(|_| fail("IA_VXACE_STAGING_FALLO"))?;
        let sha256 = file_sha256(&target)?;
        records.push(EntryRecord {
            raw_path,
            decoded_path,
            file: target,
            size: copied as usize,
            sha256,
        });
    }
    Ok(records)
}

fn write_archive(
    records: &[EntryRecord],
    output: &Path,
) -> Result<(), String> {
    if output.exists() || output.is_symlink() {
        return Err(fail("IA_VXACE_OUTPUT_EXISTS"));
    }
    let sources: Vec<DiskEntry> = records
        .iter()
        .map(|record| DiskEntry {
            raw_path: record.raw_path.clone(),
            file: record.file.clone(),
            size: record.size,
        })
        .collect();
    let file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(output)
        .map_err(|_| fail("IA_VXACE_OUTPUT_CREATE_FALLO"))?;
    let mut writer = BufWriter::new(file);
    encrypt_to_writer(&sources, Engine::Vxace, &mut writer)
        .map_err(|_| fail("IA_VXACE_ARCHIVE_ENCRYPT_FALLO"))?;
    writer.flush().map_err(|_| fail("IA_VXACE_ARCHIVE_FLUSH_FALLO"))?;
    let file = writer.into_inner().map_err(|_| fail("IA_VXACE_ARCHIVE_FLUSH_FALLO"))?;
    file.sync_all().map_err(|_| fail("IA_VXACE_ARCHIVE_SYNC_FALLO"))?;
    Ok(())
}

fn verify_repacked_archive(output: &Path, expected: &[EntryRecord]) -> Result<(), String> {
    let mut archive = decrypt_from_reader(
        File::open(output).map_err(|_| fail("IA_VXACE_OUTPUT_READ_FALLO"))?,
    )
    .map_err(|_| fail("IA_VXACE_OUTPUT_ARCHIVE_INVALIDO"))?;
    if archive.entry_count() != expected.len() {
        return Err(fail("IA_VXACE_OUTPUT_ENTRY_COUNT_MISMATCH"));
    }
    for (index, expected_entry) in expected.iter().enumerate() {
        if archive.path(index) != expected_entry.raw_path.as_slice() {
            return Err(fail("IA_VXACE_OUTPUT_PATH_MISMATCH"));
        }
        let mut reader = archive.read_entry(index).map_err(|_| fail("IA_VXACE_OUTPUT_ENTRY_READ_FALLO"))?;
        let mut hasher = Sha256::new();
        let mut buffer = [0u8; 64 * 1024];
        let mut size = 0u64;
        loop {
            let count = reader.read(&mut buffer).map_err(|_| fail("IA_VXACE_OUTPUT_ENTRY_READ_FALLO"))?;
            if count == 0 {
                break;
            }
            size = size.checked_add(count as u64).ok_or_else(|| fail("IA_VXACE_OUTPUT_ENTRY_SIZE_INVALID"))?;
            hasher.update(&buffer[..count]);
        }
        if size != expected_entry.size as u64 || format!("{:x}", hasher.finalize()) != expected_entry.sha256 {
            return Err(fail("IA_VXACE_OUTPUT_CONTENT_MISMATCH"));
        }
    }
    Ok(())
}

fn output_parent_inside_game(root: &Path, output: &Path) -> Result<(), String> {
    let parent = output.parent().ok_or_else(|| fail("IA_VXACE_OUTPUT_PATH_INVALID"))?;
    let canonical_parent = parent.canonicalize().map_err(|_| fail("IA_VXACE_OUTPUT_PATH_INVALID"))?;
    if !canonical_parent.starts_with(root) || canonical_parent == root {
        return Err(fail("IA_VXACE_OUTPUT_PATH_INVALID"));
    }
    if output.exists() || output.is_symlink() {
        return Err(fail("IA_VXACE_OUTPUT_EXISTS"));
    }
    Ok(())
}

fn install_game_root(
    root: &Path,
    plugin_path: &Path,
    output_path: &Path,
) -> Result<serde_json::Value, String> {
    let layout = validate_game_root(root)?;
    output_parent_inside_game(&layout.root, output_path)?;
    if plugin_path.is_symlink() || !ordinary(plugin_path, MAX_PLUGIN_BYTES) {
        return Err(fail("IA_VXACE_PLUGIN_NO_VERIFICADO"));
    }
    let plugin_absolute = plugin_path.canonicalize().map_err(|_| fail("IA_VXACE_PLUGIN_NO_VERIFICADO"))?;
    if !plugin_absolute.starts_with(&layout.root) {
        return Err(fail("IA_VXACE_PLUGIN_NO_VERIFICADO"));
    }
    let plugin_bytes = read_bounded(&plugin_absolute, MAX_PLUGIN_BYTES)?;
    let plugin = std::str::from_utf8(&plugin_bytes).map_err(|_| fail("IA_VXACE_PLUGIN_ENCODING_INVALIDO"))?;
    if !plugin.contains(PLUGIN_MARKER) {
        return Err(fail("IA_VXACE_PLUGIN_NO_VERIFICADO"));
    }
    let plugin_sha256 = format!("{:x}", Sha256::digest(&plugin_bytes));
    if let Some(archive_path) = layout.archive {
        let original_sha256 = file_sha256(&archive_path)?;
        let staging = TempDirBuilder::new()
            .prefix(".vxace-rgss3-")
            .tempdir_in(output_path.parent().unwrap())
            .map_err(|_| fail("IA_VXACE_STAGING_FALLO"))?;
        let mut records = extract_archive(&archive_path, staging.path())?;
        let script_indices: Vec<usize> = records
            .iter()
            .enumerate()
            .filter_map(|(index, entry)| {
                if entry.decoded_path.replace('\\', "/").eq_ignore_ascii_case("Data/Scripts.rvdata2") {
                    Some(index)
                } else {
                    None
                }
            })
            .collect();
        if script_indices.len() != 1 {
            return Err(fail("IA_VXACE_SCRIPTS_ARCHIVE_ENTRY_MISSING"));
        }
        for required in ["Data/System.rvdata2", "Data/MapInfos.rvdata2"] {
            let count = records.iter().filter(|entry| entry.decoded_path.replace('\\', "/").eq_ignore_ascii_case(required)).count();
            if count != 1 {
                return Err(fail("IA_VXACE_ARCHIVE_DATA_INCOMPLETE"));
            }
        }
        let index = script_indices[0];
        let original_scripts = read_bounded(&records[index].file, MAX_SCRIPT_BYTES)?;
        let (patched_scripts, script_index) = patch_scripts(&original_scripts, plugin)?;
        let patched_path = staging.path().join("patched-Scripts.rvdata2");
        let mut patched_file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&patched_path)
            .map_err(|_| fail("IA_VXACE_STAGING_FALLO"))?;
        patched_file.write_all(&patched_scripts).map_err(|_| fail("IA_VXACE_STAGING_FALLO"))?;
        patched_file.sync_all().map_err(|_| fail("IA_VXACE_STAGING_FALLO"))?;
        records[index].file = patched_path;
        records[index].size = patched_scripts.len();
        records[index].sha256 = file_sha256(&records[index].file)?;
        write_archive(&records, output_path)?;
        verify_repacked_archive(output_path, &records)?;
        Ok(json!({
            "schema":"servidor-vxace-install-v1",
            "mode":"rgss3a",
            "original_sha256":original_sha256,
            "output_sha256":file_sha256(output_path)?,
            "plugin_sha256":plugin_sha256,
            "script_index":script_index,
            "archive_entries":records.len(),
            "non_script_entries_preserved":true
        }))
    } else {
        let scripts_path = layout.scripts.ok_or_else(|| fail("IA_VXACE_SCRIPTS_NO_DISPONIBLE"))?;
        let original_sha256 = file_sha256(&scripts_path)?;
        let original = read_bounded(&scripts_path, MAX_SCRIPT_BYTES)?;
        let (patched, script_index) = patch_scripts(&original, plugin)?;
        if output_path.exists() || output_path.is_symlink() {
            return Err(fail("IA_VXACE_OUTPUT_EXISTS"));
        }
        let mut output = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output_path)
            .map_err(|_| fail("IA_VXACE_OUTPUT_CREATE_FALLO"))?;
        output.write_all(&patched).map_err(|_| fail("IA_VXACE_OUTPUT_WRITE_FALLO"))?;
        output.sync_all().map_err(|_| fail("IA_VXACE_OUTPUT_SYNC_FALLO"))?;
        let check = read_bounded(output_path, MAX_SCRIPT_BYTES)?;
        let _ = patch_scripts(&check, plugin)?;
        Ok(json!({
            "schema":"servidor-vxace-install-v1",
            "mode":"loose",
            "original_sha256":original_sha256,
            "output_sha256":file_sha256(output_path)?,
            "plugin_sha256":plugin_sha256,
            "script_index":script_index,
            "archive_entries":0,
            "non_script_entries_preserved":true
        }))
    }
}

fn parse_arg(args: &[String], name: &str) -> Result<PathBuf, String> {
    let index = args.iter().position(|arg| arg == name).ok_or_else(|| format!("IA_VXACE_ARG_MISSING_{name}"))?;
    args.get(index + 1)
        .map(PathBuf::from)
        .ok_or_else(|| format!("IA_VXACE_ARG_MISSING_{name}"))
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.first().map(String::as_str) != Some("install") {
        eprintln!("IA_VXACE_COMMAND_INVALID");
        std::process::exit(2);
    }
    let result = (|| {
        let root = parse_arg(&args, "--game-root")?;
        let plugin = parse_arg(&args, "--plugin")?;
        let output = parse_arg(&args, "--output")?;
        install_game_root(&root, &plugin, &output)
    })();
    match result {
        Ok(report) => println!("{}", report),
        Err(code) => {
            eprintln!("{code}");
            std::process::exit(2);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use marshal_rs::dump;
    use rvpacker_txt_rs_lib::types::Scripts;

    fn make_scripts() -> Vec<u8> {
        let scripts = Scripts::new(
            vec![101, 202],
            vec![
                "$game_message.add('Hello world')\n".to_owned(),
                "class Scene_Title\nend\n".to_owned(),
            ],
            vec!["Scene_Title".to_owned(), "Main".to_owned()],
        );
        dump(&Base::encode_scripts(&scripts))
    }

    fn make_plugin() -> String {
        format!("{PLUGIN_MARKER}\nmodule IATraductoraVXACE\nend\n")
    }

    fn make_game(root: &Path, packed: bool) -> PathBuf {
        fs::create_dir_all(root.join("Data")).unwrap();
        fs::write(root.join("Game.exe"), b"synthetic Game.exe").unwrap();
        fs::write(root.join("RGSS301.dll"), b"synthetic RGSS301.dll").unwrap();
        fs::write(
            root.join("Game.ini"),
            "[Game]\nLibrary=RGSS301.dll\nScripts=Data\\Scripts.rvdata2\nTitle=VX Ace fixture\n",
        )
        .unwrap();
        let scripts = make_scripts();
        if packed {
            let entries = vec![
                ArchiveEntry { path: b"Data\\Scripts.rvdata2", data: &scripts },
                ArchiveEntry { path: b"Data\\System.rvdata2", data: b"\x04\x08system" },
                ArchiveEntry { path: b"Data\\MapInfos.rvdata2", data: b"\x04\x08maps" },
                ArchiveEntry { path: b"Graphics\\Tilesets\\Keep.png", data: b"original-png" },
            ];
            let archive = rpgmad_lib::encrypt_to_vec(&entries, Engine::Vxace).unwrap();
            fs::write(root.join("Game.rgss3a"), archive).unwrap();
        } else {
            fs::write(root.join("Data/Scripts.rvdata2"), scripts).unwrap();
            fs::write(root.join("Data/System.rvdata2"), b"\x04\x08system").unwrap();
            fs::write(root.join("Data/MapInfos.rvdata2"), b"\x04\x08maps").unwrap();
        }
        root.to_path_buf()
    }

    #[test]
    fn loose_scripts_are_patched_without_touching_source() {
        let temp = tempfile::tempdir().unwrap();
        let root = make_game(&temp.path().join("game"), false);
        let plugin = root.join("plugin.rb");
        fs::write(&plugin, make_plugin()).unwrap();
        let output_dir = root.join("IA Traductora/.local/Rpg/staging");
        fs::create_dir_all(&output_dir).unwrap();
        let output = output_dir.join("Scripts.rvdata2.new");
        let original = fs::read(root.join("Data/Scripts.rvdata2")).unwrap();
        let report = install_game_root(&root, &plugin, &output).unwrap();
        assert_eq!(report["mode"], "loose");
        assert_eq!(fs::read(root.join("Data/Scripts.rvdata2")).unwrap(), original);
        let patched = fs::read(output).unwrap();
        let arena = load(&patched).unwrap();
        let scripts: Scripts = Base::decode_scripts(&arena, arena.root(), None).unwrap();
        let index = scripts.names.iter().position(|name| name == PLUGIN_NAME).unwrap();
        let main = scripts.names.iter().position(|name| name == "Main").unwrap();
        assert!(index < main);
        assert!(scripts.contents[index].contains(PLUGIN_MARKER));
    }

    #[test]
    fn packed_archive_is_rebuilt_and_non_script_entries_are_preserved() {
        let temp = tempfile::tempdir().unwrap();
        let root = make_game(&temp.path().join("game"), true);
        let plugin = root.join("plugin.rb");
        fs::write(&plugin, make_plugin()).unwrap();
        let output_dir = root.join("IA Traductora/.local/Rpg/staging");
        fs::create_dir_all(&output_dir).unwrap();
        let output = output_dir.join("Game.rgss3a.new");
        let before = fs::read(root.join("Game.rgss3a")).unwrap();
        let report = install_game_root(&root, &plugin, &output).unwrap();
        assert_eq!(report["mode"], "rgss3a");
        assert_eq!(fs::read(root.join("Game.rgss3a")).unwrap(), before);
        let mut archive = decrypt_from_reader(File::open(output).unwrap()).unwrap();
        let mut keep = Vec::new();
        for index in 0..archive.entry_count() {
            let path = SHIFT_JIS.decode(archive.path(index)).0.into_owned();
            if path.eq_ignore_ascii_case("Graphics\\Tilesets\\Keep.png") {
                archive.read_entry(index).unwrap().read_to_end(&mut keep).unwrap();
            }
        }
        assert_eq!(keep, b"original-png");
    }

    #[test]
    fn existing_owned_script_is_updated_idempotently() {
        let original = make_scripts();
        let plugin = make_plugin();
        let (once, _) = patch_scripts(&original, &plugin).unwrap();
        let (twice, _) = patch_scripts(&once, &plugin).unwrap();
        let arena = load(&twice).unwrap();
        let scripts: Scripts = Base::decode_scripts(&arena, arena.root(), None).unwrap();
        assert_eq!(scripts.names.iter().filter(|name| name.as_str() == PLUGIN_NAME).count(), 1);
    }
}
