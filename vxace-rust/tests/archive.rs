use encoding_rs::SHIFT_JIS;
use rpgmad_lib::{encrypt_to_vec, ArchiveEntry, Engine};
use std::io::Cursor;
use vxace_rgss3_core::{inspect_rgss3a, ArchiveInspectError, ArchiveLimits};

fn build_archive(entries: &[ArchiveEntry<'_>], engine: Engine) -> Vec<u8> {
    encrypt_to_vec(entries, engine).expect("synthetic archive should encode")
}

fn inspect(bytes: Vec<u8>, limits: &ArchiveLimits) -> Result<vxace_rgss3_core::ArchiveManifest, ArchiveInspectError> {
    inspect_rgss3a(Cursor::new(bytes), limits)
}

#[test]
fn accepts_vxace_archive_and_reports_entries_without_extracting() {
    let entries = [
        ArchiveEntry { path: b"Data\\Scripts.rvdata2", data: b"script-data" },
        ArchiveEntry { path: b"Data\\System.rvdata2", data: b"system-data" },
    ];
    let bytes = build_archive(&entries, Engine::Vxace);
    let manifest = inspect(bytes, &ArchiveLimits::default()).unwrap();

    assert_eq!(manifest.entries.len(), 2);
    assert_eq!(manifest.entries[0].path, "Data/Scripts.rvdata2");
    assert_eq!(manifest.entries[0].size, 11);
    assert_eq!(manifest.total_uncompressed_bytes, 22);
}

#[test]
fn rejects_wrong_engine_even_when_archive_header_is_valid_rgss() {
    let entries = [ArchiveEntry { path: b"Data/System.rvdata2", data: b"x" }];
    let bytes = build_archive(&entries, Engine::Older);
    assert!(matches!(inspect(bytes, &ArchiveLimits::default()), Err(ArchiveInspectError::WrongEngine)));
}

#[test]
fn rejects_non_rgss_header() {
    assert!(matches!(
        inspect(b"not-an-rgss-archive".to_vec(), &ArchiveLimits::default()),
        Err(ArchiveInspectError::InvalidHeader)
    ));
}

#[test]
fn rejects_truncated_archive() {
    let entries = [ArchiveEntry { path: b"Data/System.rvdata2", data: b"system" }];
    let mut bytes = build_archive(&entries, Engine::Vxace);
    bytes.truncate(12);
    assert!(matches!(
        inspect(bytes, &ArchiveLimits::default()),
        Err(ArchiveInspectError::InvalidArchive(_))
    ));
}

#[test]
fn rejects_parent_directory_traversal() {
    let entries = [ArchiveEntry { path: b"../outside.txt", data: b"x" }];
    let bytes = build_archive(&entries, Engine::Vxace);
    assert!(matches!(
        inspect(bytes, &ArchiveLimits::default()),
        Err(ArchiveInspectError::UnsafePath { .. })
    ));
}

#[test]
fn rejects_absolute_and_drive_qualified_paths() {
    for path in [b"/Data/System.rvdata2".as_slice(), b"C:/Data/System.rvdata2".as_slice()] {
        let entries = [ArchiveEntry { path, data: b"x" }];
        let bytes = build_archive(&entries, Engine::Vxace);
        assert!(matches!(
            inspect(bytes, &ArchiveLimits::default()),
            Err(ArchiveInspectError::UnsafePath { .. })
        ));
    }
}

#[test]
fn rejects_case_insensitive_duplicate_paths() {
    let entries = [
        ArchiveEntry { path: b"Data/System.rvdata2", data: b"one" },
        ArchiveEntry { path: b"data/system.rvdata2", data: b"two" },
    ];
    let bytes = build_archive(&entries, Engine::Vxace);
    assert!(matches!(
        inspect(bytes, &ArchiveLimits::default()),
        Err(ArchiveInspectError::DuplicatePath(_))
    ));
}

#[test]
fn decodes_shift_jis_before_splitting_backslash_byte() {
    let (encoded, _, had_errors) = SHIFT_JIS.encode("Data/表.rvdata2");
    assert!(!had_errors);
    assert!(encoded.windows(2).any(|pair| pair == [0x95, 0x5c]));
    let entries = [ArchiveEntry { path: encoded.as_ref(), data: b"japanese-path" }];
    let bytes = build_archive(&entries, Engine::Vxace);
    let manifest = inspect(bytes, &ArchiveLimits::default()).unwrap();
    assert_eq!(manifest.entries[0].path, "Data/表.rvdata2");
}

#[test]
fn enforces_entry_count_limit() {
    let entries = [
        ArchiveEntry { path: b"Data/System.rvdata2", data: b"one" },
        ArchiveEntry { path: b"Data/Scripts.rvdata2", data: b"two" },
    ];
    let bytes = build_archive(&entries, Engine::Vxace);
    let mut limits = ArchiveLimits::default();
    limits.max_entries = 1;
    assert!(matches!(inspect(bytes, &limits), Err(ArchiveInspectError::TooManyEntries)));
}

#[test]
fn enforces_per_entry_uncompressed_size_limit() {
    let entries = [ArchiveEntry { path: b"Data/System.rvdata2", data: b"longer-than-limit" }];
    let bytes = build_archive(&entries, Engine::Vxace);
    let mut limits = ArchiveLimits::default();
    limits.max_entry_bytes = 4;
    assert!(matches!(inspect(bytes, &limits), Err(ArchiveInspectError::EntryTooLarge(_))));
}

#[test]
fn enforces_total_uncompressed_size_limit() {
    let entries = [
        ArchiveEntry { path: b"Data/System.rvdata2", data: b"1234" },
        ArchiveEntry { path: b"Data/Scripts.rvdata2", data: b"5678" },
    ];
    let bytes = build_archive(&entries, Engine::Vxace);
    let mut limits = ArchiveLimits::default();
    limits.max_total_uncompressed_bytes = 6;
    assert!(matches!(inspect(bytes, &limits), Err(ArchiveInspectError::TotalTooLarge)));
}

#[test]
fn enforces_compressed_archive_size_limit() {
    let entries = [ArchiveEntry { path: b"Data/System.rvdata2", data: b"x" }];
    let bytes = build_archive(&entries, Engine::Vxace);
    let mut limits = ArchiveLimits::default();
    limits.max_archive_bytes = 7;
    assert!(matches!(inspect(bytes, &limits), Err(ArchiveInspectError::ArchiveTooLarge)));
}
