use encoding_rs::{SHIFT_JIS, WINDOWS_1252, GBK, BIG5, EUC_KR};
use marshal_rs::{dump, load};
use rpgmad_lib::{
    decrypt_from_reader, encrypt_to_writer, Engine, EntrySource,
};
use rvpacker_txt_rs_lib::{core::Base, types::Scripts};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{
    collections::HashSet,
    env,
    fs::{self, File, OpenOptions},
    io::{self, BufWriter, Read, Write},
    path::{Path, PathBuf},
};
use tempfile::Builder as TempDirBuilder;

const MAX_PLUGIN_BYTES: u64 = 1024 * 1024;
const MAX_SCRIPT_BYTES: u64 = 512 * 1024 * 1024;
// Match Go detection and Python startup, including the output limit.
const MAX_ARCHIVE_BYTES: u64 = 2 * 1024 * 1024 * 1024 - 1;
// RGSS3A is not compressed. Stream large assets; only Scripts.rvdata2 is
// deserialized in memory and retains the separate MAX_SCRIPT_BYTES cap.
const MAX_ENTRY_BYTES: u64 = MAX_ARCHIVE_BYTES;
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
    let file = File::open(path).map_err(|_| fail("IA_VXACE_ARCHIVO_NO_LEIBLE"))?;
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
    let library = library.replace('\\', "/").trim_start_matches("./").to_owned();
    let parts = library.split('/').collect::<Vec<_>>();
    if !(parts.len() == 1 || (parts.len() == 2 && parts[0].eq_ignore_ascii_case("System")))
        || !parts.last().is_some_and(|name| name.eq_ignore_ascii_case("RGSS300.dll") || name.eq_ignore_ascii_case("RGSS301.dll")) {
        return Err(fail("IA_VXACE_GAME_INI_INVALIDO"));
    }
    Ok((library, scripts))
}

fn validate_game_root(root: &Path) -> Result<GameLayout, String> {
    let root = root.canonicalize().map_err(|_| fail("IA_VXACE_JUEGO_NO_VALIDO"))?;
    if !root.is_dir() || root.symlink_metadata().map(|m| m.file_type().is_symlink()).unwrap_or(true) {
        return Err(fail("IA_VXACE_JUEGO_NO_VALIDO"));
    }
    for required in ["Game.exe", "Game.ini"] {
        if !ordinary(&root.join(required), 64 * 1024 * 1024) {
            return Err(fail("IA_VXACE_RUNTIME_NO_VERIFICADO"));
        }
    }
    let (library, _) = ini_values(&root.join("Game.ini"))?;
    let library_path = root.join(library);
    let library_parent = library_path.parent().ok_or_else(|| fail("IA_VXACE_RUNTIME_NO_VERIFICADO"))?;
    if library_parent.is_symlink() || !ordinary(&library_path, 64 * 1024 * 1024) {
        return Err(fail("IA_VXACE_RUNTIME_NO_VERIFICADO"));
    }
    for incompatible in ["Game.rgssad", "Game.rgss2a"] {
        if root.join(incompatible).symlink_metadata().is_ok() { return Err(fail("IA_VXACE_ARCHIVO_DE_OTRO_MOTOR")); }
    }
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
    // The script decoder requires an owned arena; keep all backing bytes
    // scoped to this operation instead of leaking them for a static borrow.
    let arena = load(original).map_err(|_| fail("IA_VXACE_MARSHAL_INVALIDO"))?.into_owned();
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
    let check = load(&encoded).map_err(|_| fail("IA_VXACE_MARSHAL_WRITE_INVALIDO"))?.into_owned();
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

// Archive member names are not filesystem paths in this installer. Preserve
// their original bytes in the repacked table. Decode strictly only to check
// path components and case-insensitive duplicates; never transcode a name.
fn normalized_raw_path(raw: &[u8]) -> Vec<u8> {
    raw.iter().map(|b| if *b == b'\\' { b'/' } else { b.to_ascii_lowercase() }).collect()
}

fn ascii_archive_path_eq(raw: &[u8], expected: &str) -> bool {
    raw.is_ascii() && normalized_raw_path(raw) == expected.as_bytes()
}

fn safe_archive_path(raw: &[u8], index: usize) -> Result<String, String> {
    let unsafe_path = || format!("IA_VXACE_PATH_UNSAFE_{index}");
    // These bytes cannot occur as a continuation byte in the supported
    // multibyte filename encodings. The raw check also forbids ASCII
    // traversal components even if the encoding is ambiguous.
    if raw.is_empty() || matches!(raw.first(), Some(b'/' | b'\\'))
        || raw.iter().any(|b| *b < 0x20 || *b == 0x7f || *b == b':')
        || raw.split(|b| *b == b'/' || *b == b'\\')
            .any(|part| part == b"." || part == b"..")
    {
        return Err(unsafe_path());
    }
    let decoded = if let Ok(value) = std::str::from_utf8(raw) {
        value.to_owned()
    } else if let Some(value) = [SHIFT_JIS, GBK, BIG5, EUC_KR, WINDOWS_1252]
        .iter()
        .find_map(|encoding| encoding.decode_without_bom_handling_and_without_replacement(raw))
    {
        value.into_owned()
    } else {
        // Some legacy archives contain opaque, mixed-codepage bytes. A
        // one-byte-to-one-codepoint view is reversible, unlike U+FFFD.
        // No decoded view is ever used to name an extracted host file.
        raw.iter().map(|byte| char::from(*byte)).collect()
    };
    // Split the decoded view rather than treating a multibyte trail 0x5c
    // as a separator (e.g. Shift-JIS ソ). Reject rooted, empty and traversal
    // components and retain the original safety policy.
    if decoded.split(['/', '\\']).any(|part|
        part.is_empty() || part == "." || part == ".." ||
        part.contains(':') || part.contains('\0'))
    {
        return Err(unsafe_path());
    }
    Ok(decoded)
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
    let mut seen_raw = HashSet::with_capacity(count);
    let mut records = Vec::with_capacity(count);
    let mut total = 0u64;
    for index in 0..count {
        let raw_path = archive.path(index).to_vec();
        let decoded_path = safe_archive_path(&raw_path, index)?;
        let duplicate = decoded_path.replace('\\', "/").to_lowercase();
        if !seen_raw.insert(normalized_raw_path(&raw_path)) || !seen.insert(duplicate) {
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
        // The decoded payload cannot legitimately exceed the encrypted
        // container itself. Bound overlapping or malformed entry tables too.
        let allowance = MAX_ENTRY_BYTES.min(archive_bytes.saturating_sub(total));
        let copied = io::copy(&mut reader.take(allowance + 1), &mut output).map_err(|_| fail("IA_VXACE_ARCHIVE_READ_FALLO"))?;
        if copied > allowance { return Err(fail("IA_VXACE_ARCHIVE_TOTAL_TOO_LARGE")); }
        total = total.checked_add(copied).ok_or_else(|| fail("IA_VXACE_ARCHIVE_TOTAL_TOO_LARGE"))?;
        if total > archive_bytes {
            return Err(fail("IA_VXACE_ARCHIVE_TOTAL_TOO_LARGE"));
        }
        output.sync_all().map_err(|_| fail("IA_VXACE_STAGING_FALLO"))?;
        let sha256 = file_sha256(&target)?;
        records.push(EntryRecord {
            raw_path,
            file: target,
            size: copied as usize,
            sha256,
        });
    }
    Ok(records)
}

fn archive_output_bound(records: &[EntryRecord]) -> Result<u64, String> {
    // Conservative upper bound including RGSS3A's per-entry table overhead.
    // Validate before handing offsets and sizes to the archive writer.
    let mut total = 64u64;
    for record in records {
        total = total.checked_add(64)
            .and_then(|n| n.checked_add(record.raw_path.len() as u64))
            .and_then(|n| n.checked_add(record.size as u64))
            .ok_or_else(|| fail("IA_VXACE_OUTPUT_TAMANO_INVALIDO"))?;
        if total > MAX_ARCHIVE_BYTES {
            return Err(fail("IA_VXACE_OUTPUT_TAMANO_INVALIDO"));
        }
    }
    Ok(total)
}

fn write_archive(
    records: &[EntryRecord],
    output: &Path,
) -> Result<(), String> {
    archive_output_bound(records)?;
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
    let size = file.metadata().map_err(|_| fail("IA_VXACE_OUTPUT_TAMANO_INVALIDO"))?.len();
    if size == 0 || size > MAX_ARCHIVE_BYTES {
        return Err(fail("IA_VXACE_OUTPUT_TAMANO_INVALIDO"));
    }
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
                if ascii_archive_path_eq(&entry.raw_path, "data/scripts.rvdata2") {
                    Some(index)
                } else {
                    None
                }
            })
            .collect();
        if script_indices.len() != 1 {
            return Err(fail("IA_VXACE_SCRIPTS_ARCHIVE_ENTRY_MISSING"));
        }
        for required in ["data/system.rvdata2", "data/mapinfos.rvdata2"] {
            let count = records.iter().filter(|entry| ascii_archive_path_eq(&entry.raw_path, required)).count();
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


const RUNTIME_BUILD: &str = "VXACE-RGSS3-20261126-F";
const SIDECAR: &str = "IA Traductora/.local/Rpg";
fn safe_runtime_file(root: &Path, relative: &str, maximum: u64) -> Result<PathBuf, String> {
    let mut file = root.to_owned();
    for component in Path::new(relative).components() {
        let std::path::Component::Normal(part) = component else {
            return Err(fail("IA_VXACE_RUNTIME_RUTA_INVALIDA"));
        };
        file.push(part);
        let meta = file.symlink_metadata().map_err(|_| fail("IA_VXACE_RUNTIME_NO_VERIFICADO"))?;
        if meta.file_type().is_symlink() {
            return Err(fail("IA_VXACE_RUNTIME_RUTA_INVALIDA"));
        }
        #[cfg(windows)]
        {
            use std::os::windows::fs::MetadataExt;
            if meta.file_attributes() & 0x400 != 0 {
                return Err(fail("IA_VXACE_RUNTIME_RUTA_INVALIDA"));
            }
        }
    }
    if !ordinary(&file, maximum) ||
        !file.canonicalize().map_err(|_| fail("IA_VXACE_RUNTIME_RUTA_INVALIDA"))?.starts_with(root) {
        return Err(fail("IA_VXACE_RUNTIME_NO_VERIFICADO"));
    }
    Ok(file)
}

fn runtime_manifest(root: &Path, relative: &str) -> Result<serde_json::Value, String> {
    let path = safe_runtime_file(root, relative, 8192)?;
    let raw = read_bounded(&path, 8192)?;
    serde_json::from_slice(&raw).map_err(|_| fail("IA_VXACE_RUNTIME_MANIFIESTO_INVALIDO"))
}

fn verified_worker(root: &Path, current_helper: &Path) -> Result<PathBuf, String> {
    let layout = validate_game_root(root)?;
    let root = &layout.root;
    let owner = runtime_manifest(root, "IA Traductora/owner-v1.json")?;
    let receipt = runtime_manifest(root, "IA Traductora/install/vxace-receipt.json")?;
    if owner["schema"] != "ia-traductora-owner-v1" ||
        owner["product"] != "SERVIDOR-IA-TRADUCTORA" ||
        owner["vxace_plugin_build"] != RUNTIME_BUILD ||
        receipt["schema"] != "ia-traductora-vxace-install-v1" ||
        receipt["status"] != "INSTALLED" || receipt["build"] != RUNTIME_BUILD {
        return Err(fail("IA_VXACE_RUNTIME_PROPIEDAD_INVALIDA"));
    }
    let worker = safe_runtime_file(root, &format!("{SIDECAR}/engine/IATraductora.exe"), 450 * 1024 * 1024)?;
    let helper = safe_runtime_file(root, &format!("{SIDECAR}/engine/vxace-helper.exe"), 128 * 1024 * 1024)?;
    let plugin = safe_runtime_file(root, &format!("{SIDECAR}/engine/vxace/IATraductoraVXACE.rb"), MAX_PLUGIN_BYTES)?;
    if current_helper.canonicalize().map_err(|_| fail("IA_VXACE_HELPER_RUTA_INVALIDA"))? !=
        helper.canonicalize().map_err(|_| fail("IA_VXACE_HELPER_RUTA_INVALIDA"))? {
        return Err(fail("IA_VXACE_HELPER_RUTA_INVALIDA"));
    }
    for (file, owner_key, receipt_key) in [
        (&worker, "worker_sha256", "worker_sha256"),
        (&helper, "vxace_helper_sha256", "helper_sha256"),
        (&plugin, "vxace_plugin_sha256", "plugin_sha256"),
    ] {
        let digest = sha256_file(file)?;
        if owner[owner_key].as_str() != Some(digest.as_str()) ||
            receipt[receipt_key].as_str() != Some(digest.as_str()) {
            return Err(fail("IA_VXACE_RUNTIME_SHA_INVALIDO"));
        }
    }
    let (relative, mode, limit) = if layout.archive.is_some() {
        ("Game.rgss3a", "rgss3a", MAX_ARCHIVE_BYTES)
    } else {
        ("Data/Scripts.rvdata2", "loose", MAX_SCRIPT_BYTES)
    };
    let installed = safe_runtime_file(root, relative, limit)?;
    if receipt["target_rel"] != relative || receipt["mode"] != mode ||
        receipt["after_sha256"].as_str() != Some(sha256_file(&installed)?.as_str()) {
        return Err(fail("IA_VXACE_RUNTIME_RECURSO_MODIFICADO"));
    }
    Ok(worker)
}

// Resolve from the installed helper, not a mutable working directory. Keep
// the ordinary native path for CreateProcessW and Python argv; canonical paths
// are used solely for identity/containment comparisons.
fn runtime_root(helper: &Path) -> Result<PathBuf, String> {
    if !helper.file_name().is_some_and(|n| n.to_string_lossy().eq_ignore_ascii_case("vxace-helper.exe")) {
        return Err(fail("IA_VXACE_HELPER_RUTA_INVALIDA"));
    }
    let mut directory = helper.parent().ok_or_else(|| fail("IA_VXACE_HELPER_RUTA_INVALIDA"))?;
    for expected in ["engine", "Rpg", ".local", "IA Traductora"] {
        if !directory.file_name().is_some_and(|n| n.to_string_lossy().eq_ignore_ascii_case(expected)) {
            return Err(fail("IA_VXACE_HELPER_RUTA_INVALIDA"));
        }
        directory = directory.parent().ok_or_else(|| fail("IA_VXACE_HELPER_RUTA_INVALIDA"))?;
    }
    Ok(directory.to_owned())
}

fn startup_directory(root: &Path) -> Result<PathBuf, String> {
    let canonical = root.canonicalize().map_err(|_| fail("IA_VXACE_RUNTIME_RUTA_INVALIDA"))?;
    let mut directory = root.to_owned();
    for part in ["IA Traductora", ".local", "Rpg"] {
        directory.push(part);
        let info = directory.symlink_metadata().map_err(|_| fail("IA_VXACE_RUNTIME_RUTA_INVALIDA"))?;
        if !info.is_dir() || info.file_type().is_symlink() {
            return Err(fail("IA_VXACE_RUNTIME_RUTA_INVALIDA"));
        }
        #[cfg(windows)]
        {
            use std::os::windows::fs::MetadataExt;
            if info.file_attributes() & 0x400 != 0 {
                return Err(fail("IA_VXACE_RUNTIME_RUTA_INVALIDA"));
            }
        }
    }
    if !directory.canonicalize().map_err(|_| fail("IA_VXACE_RUNTIME_RUTA_INVALIDA"))?.starts_with(&canonical) {
        return Err(fail("IA_VXACE_RUNTIME_RUTA_INVALIDA"));
    }
    Ok(directory)
}

fn startup_record(path: &Path, data: &[u8]) -> Result<(), String> {
    if let Ok(info) = path.symlink_metadata() {
        if !info.is_file() || info.file_type().is_symlink() || info.len() > 1024 {
            return Err(fail("IA_VXACE_DIAGNOSTICO_NO_SEGURO"));
        }
        #[cfg(windows)]
        {
            use std::os::windows::fs::MetadataExt;
            if info.file_attributes() & 0x400 != 0 {
                return Err(fail("IA_VXACE_DIAGNOSTICO_NO_SEGURO"));
            }
        }
    }
    let directory = path.parent().ok_or_else(|| fail("IA_VXACE_DIAGNOSTICO_NO_SEGURO"))?;
    let mut temp = tempfile::NamedTempFile::new_in(directory).map_err(|_| fail("IA_VXACE_DIAGNOSTICO_NO_SEGURO"))?;
    temp.write_all(data).map_err(|_| fail("IA_VXACE_DIAGNOSTICO_NO_SEGURO"))?;
    temp.as_file().sync_all().map_err(|_| fail("IA_VXACE_DIAGNOSTICO_NO_SEGURO"))?;
    temp.persist(path).map_err(|_| fail("IA_VXACE_DIAGNOSTICO_NO_SEGURO"))?;
    Ok(())
}

fn launch_worker(args: &[String]) -> Result<serde_json::Value, String> {
    let parent = args.get(2).and_then(|s| s.parse::<u32>().ok()).filter(|p| *p > 0)
        .ok_or_else(|| fail("IA_VXACE_PARENT_INVALIDO"))?;
    if args.len() != 3 || args[1] != "--parent-pid" {
        return Err(fail("IA_VXACE_PARENT_INVALIDO"));
    }
    let helper = env::current_exe().map_err(|_| fail("IA_VXACE_HELPER_RUTA_INVALIDA"))?;
    let root = runtime_root(&helper)?;
    let diagnostics = startup_directory(&root)?;
    let helper_status = diagnostics.join(format!("vxace-startup-helper-{parent}.txt"));
    let worker_status = diagnostics.join(format!("vxace-startup-worker-{parent}.json"));
    let process_receipt = diagnostics.join(format!("vxace-startup-process-{parent}.json"));
    startup_record(&helper_status, b"IA_VXACE_LAUNCH_CHECKING\n")?;
    // Invalidate any previous receipt before launching. The child ID below
    // identifies the actual outer executable, not the embedded Python PID.
    startup_record(&process_receipt, b"{\"schema\":\"ia-vxace-process-v1\",\"bootloader_pid\":0}\n")?;
    let result = (|| {
        let verified = verified_worker(&root, &helper)?;
        let worker = root.join(SIDECAR).join("engine/IATraductora.exe");
        if worker.canonicalize().map_err(|_| fail("IA_VXACE_RUNTIME_RUTA_INVALIDA"))? !=
            verified.canonicalize().map_err(|_| fail("IA_VXACE_RUNTIME_RUTA_INVALIDA"))? {
            return Err(fail("IA_VXACE_RUNTIME_RUTA_INVALIDA"));
        }
        startup_record(&worker_status, b"{\"schema\":\"ia-traductora-startup-v1\",\"code\":\"IA_VXACE_WORKER_STARTING\"}\n")?;
        let mut command = std::process::Command::new(worker);
        command.current_dir(&root).arg("--game-root").arg(&root)
            .arg("--parent-pid").arg(parent.to_string())
            .arg("--diagnostic-file").arg(&worker_status)
            .stdin(std::process::Stdio::null()).stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000); // CREATE_NO_WINDOW
        }
        let child = command.spawn().map_err(|_| fail("IA_VXACE_WORKER_NO_INICIA"))?;
        // PyInstaller onefile has a bootloader and a separate Python child.
        // Record the PID returned by CreateProcess, while the child is owned
        // by this helper. Do not restart or terminate it if recording fails.
        let launched = json!({"schema":"ia-vxace-process-v1",
            "game_pid":parent,"bootloader_pid":child.id()});
        if startup_record(&process_receipt, format!("{launched}\n").as_bytes()).is_ok() {
            let _ = startup_record(&helper_status, b"IA_VXACE_WORKER_SPAWNED\n");
        } else {
            let _ = startup_record(&helper_status, b"IA_VXACE_PROCESS_RECEIPT_FAILED\n");
        }
        Ok(json!({"schema":"ia-vxace-launch-v1","pid":child.id()}))
    })();
    if let Err(ref code) = result {
        let _ = startup_record(&helper_status, format!("{code}\n").as_bytes());
    }
    result
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.first().map(String::as_str) == Some("launch-worker") {
        match launch_worker(&args) {
            Ok(report) => println!("{}", report),
            Err(code) => { eprintln!("{code}"); std::process::exit(2); }
        }
        return;
    }
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
    use rpgmad_lib::ArchiveEntry;
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
        let arena = load(&patched).unwrap().into_owned();
        let scripts: Scripts = Base::decode_scripts(&arena, arena.root(), None).unwrap();
        let index = scripts.names.iter().position(|name| name == PLUGIN_NAME).unwrap();
        let main = scripts.names.iter().position(|name| name == "Main").unwrap();
        assert!(index < main);
        assert!(scripts.contents[index].contains(PLUGIN_MARKER));
        // Removing the inserted plugin must recover every original script ID,
        // name and body in the same order, not just the Main entry.
        let before = load(&original).unwrap().into_owned();
        let expected = Base::decode_scripts(&before, before.root(), None).unwrap();
        let mut restored = scripts;
        restored.numbers.remove(index);
        restored.names.remove(index);
        restored.contents.remove(index);
        assert_eq!(restored.numbers, expected.numbers);
        assert_eq!(restored.names, expected.names);
        assert_eq!(restored.contents, expected.contents);
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
    fn mixed_encoded_archive_names_are_safe_without_renaming() {
        let utf8 = "Graphics\\雪☃.png".as_bytes();
        let cp1252 = b"Graphics\\Caf\xe9.png";
        let sjis = b"Graphics\\\x83\x5c\\asset.png";
        assert!(SHIFT_JIS.decode(cp1252).2, "fixture must reproduce the R33 error");
        assert_eq!(safe_archive_path(cp1252, 307).unwrap(), "Graphics\\Café.png");
        assert_eq!(safe_archive_path(utf8, 308).unwrap(), "Graphics\\雪☃.png");
        assert_eq!(safe_archive_path(sjis, 309).unwrap(), "Graphics\\ソ\\asset.png");
        assert!(safe_archive_path(b"Graphics\\legacy-\xff.bin", 310).is_ok());
        assert!(ascii_archive_path_eq(b"DATA\\Scripts.rvdata2", "data/scripts.rvdata2"));
        assert!(!ascii_archive_path_eq(b"Data\\Script\xe9.rvdata2", "data/scripts.rvdata2"));
        assert_eq!(normalized_raw_path(b"Graphics\\A.png"), normalized_raw_path(b"graphics/a.PNG"));
        for unsafe_name in [
            b"".as_slice(), b"../bad.png", b"Graphics\\..\\bad.png", b"Graphics\\.\\bad.png",
            b"\\absolute", b"/absolute", b"C:\\bad.png", b"Graphics\\file:stream",
            b"Graphics\\a\0b.png", b"Graphics\\\x1fb.png", b"Graphics//bad.png",
            b"Graphics\\\xe9\\..\\bad.png", b"Graphics\\",
        ] {
            assert_eq!(safe_archive_path(unsafe_name, 311).unwrap_err(), "IA_VXACE_PATH_UNSAFE_311");
        }
    }

    #[test]
    fn mixed_encoding_roundtrip_preserves_original_name_bytes_and_payloads() {
        let temp = tempfile::tempdir().unwrap();
        let root = make_game(&temp.path().join("game"), true);
        let scripts = make_scripts();
        let names: &[&[u8]] = &[
            b"Graphics\\Caf\xe9.png",
            "Graphics\\雪☃.png".as_bytes(),
            b"Graphics\\\x83\x5c\\asset.png",
            b"Graphics\\legacy-\xff.bin",
        ];
        let mut entries = vec![
            ArchiveEntry { path: b"Data\\Scripts.rvdata2", data: &scripts },
            ArchiveEntry { path: b"Data\\System.rvdata2", data: b"\x04\x08system" },
            ArchiveEntry { path: b"Data\\MapInfos.rvdata2", data: b"\x04\x08maps" },
        ];
        for path in names {
            entries.push(ArchiveEntry { path, data: b"untouched multilingual asset" });
        }
        let archive = root.join("Game.rgss3a");
        let original = rpgmad_lib::encrypt_to_vec(&entries, Engine::Vxace).unwrap();
        fs::write(&archive, &original).unwrap();
        let plugin = root.join("plugin.rb");
        fs::write(&plugin, make_plugin()).unwrap();
        let staging = root.join("IA Traductora/.local/Rpg/staging");
        fs::create_dir_all(&staging).unwrap();
        let out = staging.join("Game.rgss3a.new");
        let report = install_game_root(&root, &plugin, &out).unwrap();
        assert_eq!(report["archive_entries"], 7);
        assert_eq!(fs::read(&archive).unwrap(), original);
        let mut patched = decrypt_from_reader(File::open(&out).unwrap()).unwrap();
        for (index, name) in names.iter().enumerate() {
            assert_eq!(patched.path(index + 3), *name);
            let mut bytes = Vec::new();
            patched.read_entry(index + 3).unwrap().read_to_end(&mut bytes).unwrap();
            assert_eq!(bytes, b"untouched multilingual asset");
        }
        // The archive writer may permit aliases; our installer must refuse
        // them before publication regardless of separator or case.
        entries.push(ArchiveEntry { path: b"data/scripts.RVDATA2", data: &scripts });
        fs::write(&archive, rpgmad_lib::encrypt_to_vec(&entries, Engine::Vxace).unwrap()).unwrap();
        let bad = staging.join("duplicate.new");
        assert_eq!(install_game_root(&root, &plugin, &bad).unwrap_err(), "IA_VXACE_ARCHIVE_DUPLICATE_PATH");
        assert!(!bad.exists());
    }

    #[test]
    fn large_packed_size_gate_and_output_bound() {
        let temp = tempfile::tempdir().unwrap();
        let root = make_game(&temp.path().join("game"), true);
        let path = root.join("Game.rgss3a");
        let file = OpenOptions::new().write(true).open(&path).unwrap();
        file.set_len(1_216_546 * 1024).unwrap();
        assert!(validate_game_root(&root).unwrap().archive.is_some());
        file.set_len(MAX_ARCHIVE_BYTES + 1).unwrap();
        assert!(validate_game_root(&root).is_err());
        drop(file);
        let mut record = EntryRecord {
            raw_path: b"Graphics/large.bin".to_vec(),
            file: path,
            size: 1_216_546 * 1024,
            sha256: String::new(),
        };
        assert!(archive_output_bound(&[record.clone()]).is_ok());
        record.size = MAX_ARCHIVE_BYTES as usize;
        assert!(archive_output_bound(&[record]).is_err());
    }

    #[test]
    fn existing_owned_script_is_updated_idempotently() {
        let original = make_scripts();
        let plugin = make_plugin();
        let (once, _) = patch_scripts(&original, &plugin).unwrap();
        let (twice, _) = patch_scripts(&once, &plugin).unwrap();
        assert_eq!(once, twice, "reinstalling the identical owned script must not rewrite bytes");
        let arena = load(&twice).unwrap().into_owned();
        let scripts: Scripts = Base::decode_scripts(&arena, arena.root(), None).unwrap();
        assert_eq!(scripts.names.iter().filter(|name| name.as_str() == PLUGIN_NAME).count(), 1);
    }
}
