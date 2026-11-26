use super::{checked_root, decode_archive_path, has_loose_rvdata2, sha256, MAX_ARCHIVE, MAX_ENTRIES, MAX_ENTRY, MAX_TOTAL_DATA};
use rpgmad_lib::{decrypt_from_reader, encrypt_to_vec, ArchiveEntry, Engine};
use rvpacker_txt_rs_lib::{json, EngineType};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use tempfile::NamedTempFile;

const RECEIPT_SCHEMA: &str = "tenshixgame-rgss3-install-v1";
const PLUGIN_NAME: &str = "TENSHIXGAME RGSS3 Runtime";
const PLUGIN_MARKER: &str = "TENSHIXGAME_RGSS3_RUNTIME_V1";
const MAX_PLUGIN_BYTES: u64 = 512 * 1024;

struct Entry {
    path: Vec<u8>,
    data: Vec<u8>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Receipt {
    pub schema: String,
    pub state: String,
    pub original_sha256: String,
    pub installed_sha256: String,
    pub plugin_sha256: String,
    pub backup: String,
}

fn hash_bytes(bytes: &[u8]) -> String {
    let mut hash = Sha256::new();
    hash.update(bytes);
    format!("{:x}", hash.finalize())
}

fn game_archive(root: &Path) -> Result<PathBuf, String> {
    if !root.join("Game.exe").is_file() || !root.join("Game.ini").is_file() {
        return Err("IA_RGSS3_GAME_MARKERS_INVALIDOS".into());
    }
    let archive = root.join("Game.rgss3a");
    if !archive.is_file() || archive.is_symlink() {
        return Err("IA_RGSS3_ARCHIVE_NO_VALIDO".into());
    }
    if has_loose_rvdata2(&root.join("Data"))? {
        return Err("IA_RGSS3_LAYOUT_AMBIGUO".into());
    }
    let size = fs::metadata(&archive)
        .map_err(|_| "IA_RGSS3_ARCHIVE_NO_LEIBLE".to_string())?
        .len();
    if !(8..=MAX_ARCHIVE).contains(&size) {
        return Err("IA_RGSS3_ARCHIVE_TAMANO_INVALIDO".into());
    }
    let mut header = [0u8; 8];
    File::open(&archive)
        .and_then(|mut file| file.read_exact(&mut header))
        .map_err(|_| "IA_RGSS3_ARCHIVE_NO_LEIBLE".to_string())?;
    if &header[..7] != b"RGSSAD\0" || header[7] != 3 {
        return Err("IA_RGSS3_ARCHIVE_NO_VALIDO".into());
    }
    Ok(archive)
}

fn read_entries(path: &Path) -> Result<Vec<Entry>, String> {
    let mut archive = decrypt_from_reader(
        File::open(path).map_err(|_| "IA_RGSS3_ARCHIVE_NO_LEIBLE".to_string())?,
    )
    .map_err(|_| "IA_RGSS3_ARCHIVE_CORRUPTO_O_NO_COMPATIBLE".to_string())?;
    let count = archive.entry_count();
    if count == 0 || count > MAX_ENTRIES {
        return Err("IA_RGSS3_CANTIDAD_ENTRADAS_NO_ADMITIDA".into());
    }
    let mut names = HashSet::new();
    let mut total = 0u64;
    let mut entries = Vec::with_capacity(count);
    for index in 0..count {
        let path = archive.path(index).to_vec();
        let relative = decode_archive_path(&path)?;
        let key = relative.to_string_lossy().replace('\\', "/").to_lowercase();
        if !names.insert(key) {
            return Err("IA_RGSS3_RUTA_DUPLICADA".into());
        }
        let mut reader = archive
            .read_entry(index)
            .map_err(|_| "IA_RGSS3_ENTRADA_NO_LEIBLE".to_string())?;
        let mut data = Vec::new();
        reader
            .by_ref()
            .take(MAX_ENTRY + 1)
            .read_to_end(&mut data)
            .map_err(|_| "IA_RGSS3_ENTRADA_LECTURA_FALLIDA".to_string())?;
        if data.len() as u64 > MAX_ENTRY {
            return Err("IA_RGSS3_ENTRADA_EXCESIVA".into());
        }
        total = total.saturating_add(data.len() as u64);
        if total > MAX_TOTAL_DATA {
            return Err("IA_RGSS3_EXPANSION_EXCESIVA".into());
        }
        entries.push(Entry { path, data });
    }
    Ok(entries)
}

fn scripts_index(entries: &[Entry]) -> Result<usize, String> {
    let found: Vec<usize> = entries
        .iter()
        .enumerate()
        .filter_map(|(index, entry)| {
            let path = String::from_utf8_lossy(&entry.path)
                .replace('\\', "/")
                .to_ascii_lowercase();
            if path == "data/scripts.rvdata2" {
                Some(index)
            } else {
                None
            }
        })
        .collect();
    if found.len() != 1 {
        return Err("IA_RGSS3_SCRIPTS_RVdata2_NO_UNICO".into());
    }
    Ok(found[0])
}

struct ScriptSection {
    header: String,
    id: i32,
    name: String,
    body: String,
}

fn parse_scripts_export(source: &str) -> Result<(String, Vec<ScriptSection>), String> {
    let marker = "<!>SCRIPT<#>";
    let mut prefix = String::new();
    let mut sections: Vec<ScriptSection> = Vec::new();
    let mut current: Option<ScriptSection> = None;
    for line in source.split_inclusive('\n') {
        if line.starts_with(marker) {
            if let Some(section) = current.take() {
                sections.push(section);
            }
            let header = line.trim_end_matches(&['\r', '\n'][..]);
            let fields = header
                .strip_prefix(marker)
                .ok_or_else(|| "IA_RGSS3_SCRIPT_HEADER_INVALIDO".to_string())?;
            let (id, name) = fields
                .split_once("<#>")
                .ok_or_else(|| "IA_RGSS3_SCRIPT_HEADER_INVALIDO".to_string())?;
            let id = id
                .parse::<i32>()
                .map_err(|_| "IA_RGSS3_SCRIPT_ID_INVALIDO".to_string())?;
            current = Some(ScriptSection {
                header: line.to_string(),
                id,
                name: name.to_string(),
                body: String::new(),
            });
        } else if let Some(section) = current.as_mut() {
            section.body.push_str(line);
        } else {
            prefix.push_str(line);
        }
    }
    if let Some(section) = current {
        sections.push(section);
    }
    if sections.is_empty() {
        return Err("IA_RGSS3_SCRIPTS_EXPORT_VACIO".into());
    }
    Ok((prefix, sections))
}

fn inject_script_export(source: &str, plugin: &str) -> Result<String, String> {
    if !plugin.contains(PLUGIN_MARKER) {
        return Err("IA_RGSS3_PLUGIN_MARKER_AUSENTE".into());
    }
    let (prefix, mut sections) = parse_scripts_export(source)?;
    let marker_matches: Vec<usize> = sections
        .iter()
        .enumerate()
        .filter_map(|(index, section)| {
            if section.body.contains(PLUGIN_MARKER) {
                Some(index)
            } else {
                None
            }
        })
        .collect();
    let named_index = sections
        .iter()
        .position(|section| section.name == PLUGIN_NAME);
    if !marker_matches.is_empty() {
        if marker_matches.len() != 1 || named_index != marker_matches.first().copied() {
            return Err("IA_RGSS3_PLUGIN_MARKER_COLLISION".into());
        }
        sections[marker_matches[0]].body = ensure_trailing_newline(plugin.to_string());
    } else if named_index.is_some() {
        return Err("IA_RGSS3_SCRIPT_NAME_COLLISION".into());
    } else {
        let id = sections.iter().map(|section| section.id).max().unwrap_or(0) + 1;
        let newline = if source.contains("\r\n") { "\r\n" } else { "\n" };
        let header = format!("<!>SCRIPT<#>{}<#>{}{}", id, PLUGIN_NAME, newline);
        let new_section = ScriptSection {
            header,
            id,
            name: PLUGIN_NAME.to_string(),
            body: ensure_trailing_newline(plugin.to_string()),
        };
        let main_index = sections
            .iter()
            .position(|section| section.name.trim().eq_ignore_ascii_case("main"))
            .unwrap_or(sections.len());
        sections.insert(main_index, new_section);
    }

    let mut result = prefix;
    for section in sections {
        result.push_str(&section.header);
        result.push_str(&section.body);
        if !result.ends_with('\n') {
            result.push('\n');
        }
    }
    Ok(result)
}

fn ensure_trailing_newline(mut value: String) -> String {
    if !value.ends_with('\n') {
        value.push('\n');
    }
    value
}

fn rewrite_scripts(scripts_bytes: &[u8], plugin: &str) -> Result<Vec<u8>, String> {
    let exported = json::generate_file(scripts_bytes, "Scripts.rvdata2", None)
        .map_err(|_| "IA_RGSS3_MARSHAL_SCRIPTS_INVALIDO".to_string())?;
    let modified = inject_script_export(&exported, plugin)?;
    let temp = tempfile::tempdir().map_err(|_| "IA_RGSS3_TEMP_NO_DISPONIBLE".to_string())?;
    let input = temp.path().join("json");
    let output = temp.path().join("out");
    fs::create_dir_all(&input).map_err(|_| "IA_RGSS3_TEMP_NO_DISPONIBLE".to_string())?;
    fs::write(input.join("Scripts.rb"), modified)
        .map_err(|_| "IA_RGSS3_TEMP_SCRIPT_NO_ESCRIBIBLE".to_string())?;
    json::write(&input, &output, EngineType::VXAce, None)
        .map_err(|_| "IA_RGSS3_MARSHAL_SCRIPTS_NO_RECONSTRUIBLE".to_string())?;
    let result = fs::read(output.join("Scripts.rvdata2"))
        .map_err(|_| "IA_RGSS3_SCRIPTS_RECONSTRUIDO_AUSENTE".to_string())?;
    let verify = json::generate_file(&result, "Scripts.rvdata2", None)
        .map_err(|_| "IA_RGSS3_SCRIPTS_RECONSTRUIDO_INVALIDO".to_string())?;
    if !verify.contains(PLUGIN_MARKER) {
        return Err("IA_RGSS3_SCRIPTS_PLUGIN_NO_VERIFICADO".into());
    }
    Ok(result)
}

fn encrypt_entries(entries: &[Entry]) -> Result<Vec<u8>, String> {
    let refs: Vec<ArchiveEntry<'_>> = entries
        .iter()
        .map(|entry| ArchiveEntry {
            path: &entry.path,
            data: &entry.data,
        })
        .collect();
    encrypt_to_vec(&refs, Engine::Vxace)
        .map_err(|_| "IA_RGSS3_ARCHIVE_RECONSTRUCCION_FALLIDA".to_string())
}

fn verify_archive_preservation(before: &[Entry], after: &[u8], scripts_path: &[u8]) -> Result<(), String> {
    let mut archive = decrypt_from_reader(std::io::Cursor::new(after))
        .map_err(|_| "IA_RGSS3_ARCHIVE_REBUILD_NO_LEIBLE".to_string())?;
    if archive.entry_count() != before.len() {
        return Err("IA_RGSS3_ARCHIVE_ENTRY_COUNT_CHANGED".into());
    }
    let mut script_changed = false;
    for index in 0..archive.entry_count() {
        let path = archive.path(index).to_vec();
        if path != before[index].path {
            return Err("IA_RGSS3_ARCHIVE_PATH_ORDER_CHANGED".into());
        }
        let mut actual = Vec::new();
        archive
            .read_entry(index)
            .map_err(|_| "IA_RGSS3_ARCHIVE_ENTRY_NO_LEIBLE".to_string())?
            .read_to_end(&mut actual)
            .map_err(|_| "IA_RGSS3_ARCHIVE_ENTRY_READ_FAILED".to_string())?;
        if path == scripts_path {
            script_changed = actual != before[index].data;
        } else if actual != before[index].data {
            return Err("IA_RGSS3_ARCHIVE_NON_SCRIPT_ENTRY_CHANGED".into());
        }
    }
    if !script_changed {
        return Err("IA_RGSS3_SCRIPTS_NO_CAMBIARON".into());
    }
    Ok(())
}

fn ensure_safe_dir(root: &Path, parts: &[&str]) -> Result<PathBuf, String> {
    let mut current = root.to_path_buf();
    for part in parts {
        current.push(part);
        if current.exists() {
            let meta = fs::symlink_metadata(&current)
                .map_err(|_| "IA_RGSS3_SIDECAR_PATH_INVALID".to_string())?;
            if meta.file_type().is_symlink() || !meta.is_dir() {
                return Err("IA_RGSS3_SIDECAR_PATH_INVALID".into());
            }
        } else {
            fs::create_dir(&current)
                .map_err(|_| "IA_RGSS3_SIDECAR_DIR_CREATE_FAILED".to_string())?;
        }
    }
    Ok(current)
}

fn safe_backup_path(root: &Path, relative: &str) -> Result<PathBuf, String> {
    let rel = Path::new(relative);
    if rel.is_absolute()
        || rel.components().any(|component| !matches!(component, std::path::Component::Normal(_)))
    {
        return Err("IA_RGSS3_BACKUP_PATH_INVALID".into());
    }
    let full = root.join(rel);
    if !full.starts_with(root) {
        return Err("IA_RGSS3_BACKUP_PATH_INVALID".into());
    }
    let mut current = root.to_path_buf();
    for component in rel.components() {
        current.push(component.as_os_str());
        if current.exists() && fs::symlink_metadata(&current)
            .map_err(|_| "IA_RGSS3_BACKUP_PATH_INVALID".to_string())?
            .file_type().is_symlink()
        {
            return Err("IA_RGSS3_BACKUP_PATH_INVALID".into());
        }
    }
    Ok(full)
}

fn backup_path(root: &Path, original_sha: &str) -> PathBuf {
    root.join("IA Traductora")
        .join(".backups")
        .join("rgss3")
        .join(format!("Game.rgss3a.{}.bak", original_sha))
}

fn receipt_path(root: &Path) -> PathBuf {
    root.join("IA Traductora")
        .join(".local")
        .join("Rpg")
        .join("rgss3-install.json")
}

fn write_backup(root: &Path, source: &Path, destination: &Path, expected_sha: &str) -> Result<(), String> {
    ensure_safe_dir(root, &["IA Traductora", ".backups", "rgss3"])?;
    if let Some(parent) = destination.parent() {
        if !parent.is_dir() {
            return Err("IA_RGSS3_BACKUP_DIR_FAILED".into());
        }
    }
    if destination.exists() {
        if sha256(destination)? != expected_sha {
            return Err("IA_RGSS3_BACKUP_COLLISION".into());
        }
        return Ok(());
    }
    let mut input = File::open(source).map_err(|_| "IA_RGSS3_ARCHIVE_NO_LEIBLE".to_string())?;
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(destination)
        .map_err(|_| "IA_RGSS3_BACKUP_CREATE_FAILED".to_string())?;
    std::io::copy(&mut input, &mut output).map_err(|_| "IA_RGSS3_BACKUP_COPY_FAILED".to_string())?;
    output.sync_all().map_err(|_| "IA_RGSS3_BACKUP_SYNC_FAILED".to_string())?;
    if sha256(destination)? != expected_sha {
        return Err("IA_RGSS3_BACKUP_HASH_MISMATCH".into());
    }
    Ok(())
}

fn atomic_replace(bytes: &[u8], destination: &Path) -> Result<(), String> {
    let parent = destination
        .parent()
        .ok_or_else(|| "IA_RGSS3_ATOMIC_PARENT_INVALID".to_string())?;
    let mut temp = NamedTempFile::new_in(parent)
        .map_err(|_| "IA_RGSS3_ATOMIC_TEMP_FAILED".to_string())?;
    temp.write_all(bytes).map_err(|_| "IA_RGSS3_ATOMIC_WRITE_FAILED".to_string())?;
    temp.as_file()
        .sync_all()
        .map_err(|_| "IA_RGSS3_ATOMIC_SYNC_FAILED".to_string())?;
    let temp_path = temp.into_temp_path();
    replace_path(&temp_path, destination)?;
    Ok(())
}

#[cfg(windows)]
fn replace_path(source: &Path, destination: &Path) -> Result<(), String> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{
        MoveFileExW, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH,
    };
    let source_wide: Vec<u16> = source.as_os_str().encode_wide().chain(Some(0)).collect();
    let destination_wide: Vec<u16> = destination.as_os_str().encode_wide().chain(Some(0)).collect();
    let result = unsafe {
        MoveFileExW(
            source_wide.as_ptr(),
            destination_wide.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if result == 0 {
        return Err("IA_RGSS3_ATOMIC_REPLACE_FAILED".into());
    }
    Ok(())
}

#[cfg(not(windows))]
fn replace_path(source: &Path, destination: &Path) -> Result<(), String> {
    fs::rename(source, destination).map_err(|_| "IA_RGSS3_ATOMIC_REPLACE_FAILED".to_string())
}

fn write_receipt(root: &Path, receipt: &Receipt) -> Result<(), String> {
    let parent = ensure_safe_dir(root, &["IA Traductora", ".local", "Rpg"])?;
    let path = parent.join("rgss3-install.json");
    let bytes = serde_json::to_vec_pretty(receipt)
        .map_err(|_| "IA_RGSS3_RECEIPT_SERIALIZE_FAILED".to_string())?;
    atomic_replace(&bytes, &path)
}

fn read_receipt(root: &Path) -> Result<Receipt, String> {
    let bytes = fs::read(receipt_path(root))
        .map_err(|_| "IA_RGSS3_RECEIPT_MISSING".to_string())?;
    let receipt: Receipt =
        serde_json::from_slice(&bytes).map_err(|_| "IA_RGSS3_RECEIPT_INVALID".to_string())?;
    if receipt.schema != RECEIPT_SCHEMA {
        return Err("IA_RGSS3_RECEIPT_SCHEMA_INVALID".into());
    }
    Ok(receipt)
}

pub fn install(game: &Path, plugin_path: &Path) -> Result<Receipt, String> {
    let root = checked_root(game)?;
    let archive = game_archive(&root)?;
    if !plugin_path.is_file() || plugin_path.is_symlink() {
        return Err("IA_RGSS3_PLUGIN_FILE_INVALID".into());
    }
    let plugin_meta = fs::metadata(plugin_path)
        .map_err(|_| "IA_RGSS3_PLUGIN_FILE_INVALID".to_string())?;
    if plugin_meta.len() == 0 || plugin_meta.len() > MAX_PLUGIN_BYTES {
        return Err("IA_RGSS3_PLUGIN_SIZE_INVALID".into());
    }
    let plugin = fs::read_to_string(plugin_path)
        .map_err(|_| "IA_RGSS3_PLUGIN_ENCODING_INVALID".to_string())?;
    if !plugin.contains(PLUGIN_MARKER) {
        return Err("IA_RGSS3_PLUGIN_MARKER_AUSENTE".into());
    }

    if receipt_path(&root).exists() {
        let mut old = read_receipt(&root)?;
        let current_sha = sha256(&archive)?;
        if old.state == "INSTALLED" {
            if current_sha == old.installed_sha256 {
                return Err("IA_RGSS3_ALREADY_INSTALLED".into());
            }
            return Err("IA_RGSS3_INSTALLED_ARCHIVE_CHANGED".into());
        }
        if old.state == "PREPARED" {
            if current_sha == old.installed_sha256 {
                old.state = "INSTALLED".to_string();
                write_receipt(&root, &old)?;
                return Ok(old);
            }
            if current_sha != old.original_sha256 {
                return Err("IA_RGSS3_PREPARED_ARCHIVE_CHANGED".into());
            }
        }
    }

    let original_sha = sha256(&archive)?;
    let mut entries = read_entries(&archive)?;
    let index = scripts_index(&entries)?;
    let scripts_path = entries[index].path.clone();
    let new_scripts = rewrite_scripts(&entries[index].data, &plugin)?;
    entries[index].data = new_scripts;

    let rebuilt = encrypt_entries(&entries)?;
    verify_archive_preservation(
        &read_entries(&archive)?,
        &rebuilt,
        &scripts_path,
    )?;
    if rebuilt.len() as u64 > MAX_ARCHIVE {
        return Err("IA_RGSS3_REBUILT_ARCHIVE_TOO_LARGE".into());
    }
    let installed_sha = hash_bytes(&rebuilt);
    let plugin_sha = hash_bytes(plugin.as_bytes());
    let backup = backup_path(&root, &original_sha);
    write_backup(&root, &archive, &backup, &original_sha)?;

    let relative_backup = backup
        .strip_prefix(&root)
        .map_err(|_| "IA_RGSS3_BACKUP_PATH_INVALID".to_string())?
        .to_string_lossy()
        .replace('\\', "/");
    let mut receipt = Receipt {
        schema: RECEIPT_SCHEMA.to_string(),
        state: "PREPARED".to_string(),
        original_sha256: original_sha,
        installed_sha256: installed_sha,
        plugin_sha256: plugin_sha,
        backup: relative_backup,
    };
    write_receipt(&root, &receipt)?;
    atomic_replace(&rebuilt, &archive)?;
    if sha256(&archive)? != receipt.installed_sha256 {
        return Err("IA_RGSS3_INSTALLED_HASH_MISMATCH".into());
    }
    receipt.state = "INSTALLED".to_string();
    write_receipt(&root, &receipt)?;
    Ok(receipt)
}

pub fn restore(game: &Path) -> Result<Receipt, String> {
    let root = checked_root(game)?;
    let archive = root.join("Game.rgss3a");
    let mut receipt = read_receipt(&root)?;
    let backup = safe_backup_path(&root, &receipt.backup)?;
    if !backup.is_file() || backup.is_symlink() {
        return Err("IA_RGSS3_BACKUP_PATH_INVALID".into());
    }
    if sha256(&backup)? != receipt.original_sha256 {
        return Err("IA_RGSS3_BACKUP_HASH_MISMATCH".into());
    }
    let current = sha256(&archive)?;
    if receipt.state == "RESTORED" && current == receipt.original_sha256 {
        return Ok(receipt);
    }
    if receipt.state == "PREPARED" && current == receipt.original_sha256 {
        receipt.state = "RESTORED".to_string();
        write_receipt(&root, &receipt)?;
        return Ok(receipt);
    }
    if !matches!(receipt.state.as_str(), "INSTALLED" | "PREPARED")
        || current != receipt.installed_sha256
    {
        return Err("IA_RGSS3_CURRENT_ARCHIVE_CHANGED".into());
    }
    let bytes = fs::read(&backup).map_err(|_| "IA_RGSS3_BACKUP_READ_FAILED".to_string())?;
    atomic_replace(&bytes, &archive)?;
    if sha256(&archive)? != receipt.original_sha256 {
        return Err("IA_RGSS3_RESTORE_HASH_MISMATCH".into());
    }
    receipt.state = "RESTORED".to_string();
    write_receipt(&root, &receipt)?;
    Ok(receipt)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn make_scripts_data() -> Vec<u8> {
        let temp = tempfile::tempdir().unwrap();
        let input = temp.path().join("json");
        let output = temp.path().join("out");
        fs::create_dir_all(&input).unwrap();
        fs::write(
            input.join("Scripts.rb"),
            "<!>SCRIPT<#>1<#>Materials\n# materials fixture\n<!>SCRIPT<#>2<#>Main\n# main fixture\n",
        )
        .unwrap();
        json::write(&input, &output, EngineType::VXAce, None).unwrap();
        fs::read(output.join("Scripts.rvdata2")).unwrap()
    }

    fn make_archive(path: &Path) -> String {
        let scripts = make_scripts_data();
        let entries = [
            ArchiveEntry { path: b"Data\\Scripts.rvdata2", data: &scripts },
            ArchiveEntry { path: b"Data\\System.rvdata2", data: b"system-fixture" },
            ArchiveEntry { path: b"Audio\\BGM\\theme.ogg", data: b"audio-fixture" },
        ];
        let bytes = encrypt_to_vec(&entries, Engine::Vxace).unwrap();
        fs::write(path, &bytes).unwrap();
        hash_bytes(&bytes)
    }

    #[test]
    fn runtime_script_is_inserted_before_main_and_roundtrips() {
        let scripts = make_scripts_data();
        let plugin = "# TENSHIXGAME_RGSS3_RUNTIME_V1\nclass TXFixture\nend\n";
        let rewritten = rewrite_scripts(&scripts, plugin).unwrap();
        let exported = json::generate_file(&rewritten, "Scripts.rvdata2", None).unwrap();
        let plugin_pos = exported.find(PLUGIN_MARKER).unwrap();
        let main_pos = exported.find("<!>SCRIPT<#>2<#>Main").unwrap();
        assert!(plugin_pos < main_pos);
    }

    #[test]
    fn install_and_restore_are_reversible_and_preserve_non_script_entries() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path();
        fs::write(root.join("Game.exe"), b"MZ-fixture").unwrap();
        fs::write(root.join("Game.ini"), b"[Game]\nLibrary=RGSS301.dll\n").unwrap();
        let archive = root.join("Game.rgss3a");
        let original = make_archive(&archive);
        let plugin = root.join("runtime.rb");
        fs::write(&plugin, "# TENSHIXGAME_RGSS3_RUNTIME_V1\nclass TXFixture\nend\n").unwrap();

        let installed = install(root, &plugin).unwrap();
        assert_eq!(installed.state, "INSTALLED");
        assert_ne!(installed.original_sha256, installed.installed_sha256);
        assert_eq!(sha256(&archive).unwrap(), installed.installed_sha256);

        let restored = restore(root).unwrap();
        assert_eq!(restored.state, "RESTORED");
        assert_eq!(sha256(&archive).unwrap(), original);

        let mut archive = decrypt_from_reader(File::open(&archive).unwrap()).unwrap();
        assert_eq!(archive.entry_count(), 3);
        let mut seen_audio = false;
        for index in 0..archive.entry_count() {
            let path = archive.path(index).to_vec();
            let mut data = Vec::new();
            archive.read_entry(index).unwrap().read_to_end(&mut data).unwrap();
            if path.ends_with(b"theme.ogg") {
                seen_audio = data == b"audio-fixture";
            }
        }
        assert!(seen_audio);
    }
}
