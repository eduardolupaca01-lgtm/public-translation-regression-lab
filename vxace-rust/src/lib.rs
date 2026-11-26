//! Independent, read-only RGSS3A archive inspection.
//!
//! The archive decoder is consumed as a pinned library dependency. This crate
//! owns the product policy: size limits, Shift-JIS path decoding, path safety,
//! duplicate detection and bounded streaming of every entry. It never writes
//! into the source game directory.

use encoding_rs::SHIFT_JIS;
use rpgmad_lib::{decrypt_from_reader, ArchiveEntry, Engine};
use std::collections::HashSet;
use std::io::{self, Read, Seek, SeekFrom, Write};
use thiserror::Error;

const RGSS_MAGIC: &[u8; 7] = b"RGSSAD\0";
const VX_ACE_ENGINE_BYTE: u8 = 3;

#[derive(Debug, Clone)]
pub struct ArchiveLimits {
    pub max_archive_bytes: u64,
    pub max_entries: usize,
    pub max_entry_bytes: u64,
    pub max_total_uncompressed_bytes: u64,
}

impl Default for ArchiveLimits {
    fn default() -> Self {
        Self {
            max_archive_bytes: u32::MAX as u64,
            max_entries: 200_000,
            max_entry_bytes: 512 * 1024 * 1024,
            max_total_uncompressed_bytes: 4 * 1024 * 1024 * 1024,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ArchiveEntryInfo {
    pub path: String,
    pub size: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ArchiveManifest {
    pub archive_bytes: u64,
    pub total_uncompressed_bytes: u64,
    pub entries: Vec<ArchiveEntryInfo>,
}

#[derive(Debug, Error)]
pub enum ArchiveInspectError {
    #[error("archive I/O failed: {0}")]
    Io(#[from] io::Error),
    #[error("RGSS archive header is missing or invalid")]
    InvalidHeader,
    #[error("archive is not a VX Ace RGSS3A archive")]
    WrongEngine,
    #[error("archive exceeds the configured compressed-size limit")]
    ArchiveTooLarge,
    #[error("archive contains no entries")]
    EmptyArchive,
    #[error("archive entry count exceeds the configured limit")]
    TooManyEntries,
    #[error("RGSS3A parser rejected the archive: {0}")]
    InvalidArchive(String),
    #[error("archive entry {index} has an invalid Shift-JIS path")]
    InvalidPathEncoding { index: usize },
    #[error("archive entry {index} has an unsafe path: {path}")]
    UnsafePath { index: usize, path: String },
    #[error("archive contains a duplicate path: {0}")]
    DuplicatePath(String),
    #[error("archive entry exceeds the configured size limit: {0}")]
    EntryTooLarge(String),
    #[error("total uncompressed archive size exceeds the configured limit")]
    TotalTooLarge,
}

struct BoundedCounter {
    bytes: u64,
    limit: u64,
    exceeded: bool,
}

impl Write for BoundedCounter {
    fn write(&mut self, buffer: &[u8]) -> io::Result<usize> {
        let next = self.bytes.checked_add(buffer.len() as u64).ok_or_else(|| {
            io::Error::new(io::ErrorKind::InvalidData, "entry size overflow")
        })?;
        if next > self.limit {
            self.exceeded = true;
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "entry exceeds configured size limit",
            ));
        }
        self.bytes = next;
        Ok(buffer.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

fn decode_and_validate_path(raw: &[u8], index: usize) -> Result<String, ArchiveInspectError> {
    // Decode Shift-JIS before splitting separators. In Japanese Shift-JIS,
    // 0x5c can be the second byte of a character and must not be treated as '\'.
    let (decoded, _, had_errors) = SHIFT_JIS.decode(raw);
    if had_errors {
        return Err(ArchiveInspectError::InvalidPathEncoding { index });
    }
    let decoded = decoded.into_owned();
    let entry = ArchiveEntry {
        path: decoded.as_bytes(),
        data: &[],
    };
    let components = entry.path_components().ok_or_else(|| {
        ArchiveInspectError::UnsafePath {
            index,
            path: decoded.clone(),
        }
    })?;
    let components: Vec<&[u8]> = components.collect();
    if components.is_empty() {
        return Err(ArchiveInspectError::UnsafePath {
            index,
            path: decoded,
        });
    }
    let mut normalized = Vec::with_capacity(components.len());
    for component in components {
        let value = std::str::from_utf8(component).map_err(|_| {
            ArchiveInspectError::InvalidPathEncoding { index }
        })?;
        normalized.push(value);
    }
    Ok(normalized.join("/"))
}

/// Inspect a VX Ace RGSS3A archive from any seekable reader.
///
/// The parser reads and decrypts entries as a stream. No archive contents are
/// written to disk and no game files are modified.
pub fn inspect_rgss3a<R: Read + Seek>(
    mut source: R,
    limits: &ArchiveLimits,
) -> Result<ArchiveManifest, ArchiveInspectError> {
    let archive_bytes = source.seek(SeekFrom::End(0))?;
    if archive_bytes > limits.max_archive_bytes {
        return Err(ArchiveInspectError::ArchiveTooLarge);
    }
    if archive_bytes < 8 {
        return Err(ArchiveInspectError::InvalidHeader);
    }

    source.seek(SeekFrom::Start(0))?;
    let mut header = [0u8; 8];
    source.read_exact(&mut header).map_err(|_| ArchiveInspectError::InvalidHeader)?;
    if &header[..7] != RGSS_MAGIC {
        return Err(ArchiveInspectError::InvalidHeader);
    }
    if header[7] != VX_ACE_ENGINE_BYTE {
        return Err(ArchiveInspectError::WrongEngine);
    }

    source.seek(SeekFrom::Start(0))?;
    let mut archive = decrypt_from_reader(source)
        .map_err(|error| ArchiveInspectError::InvalidArchive(error.to_string()))?;

    let count = archive.entry_count();
    if count == 0 {
        return Err(ArchiveInspectError::EmptyArchive);
    }
    if count > limits.max_entries {
        return Err(ArchiveInspectError::TooManyEntries);
    }

    let mut seen = HashSet::with_capacity(count);
    let mut entries = Vec::with_capacity(count);
    let mut total_uncompressed_bytes = 0u64;

    for index in 0..count {
        let path = decode_and_validate_path(archive.path(index), index)?;
        let duplicate_key = path.to_lowercase();
        if !seen.insert(duplicate_key) {
            return Err(ArchiveInspectError::DuplicatePath(path));
        }

        let mut reader = archive.read_entry(index)?;
        let mut counter = BoundedCounter {
            bytes: 0,
            limit: limits.max_entry_bytes,
            exceeded: false,
        };
        if let Err(error) = io::copy(&mut reader, &mut counter) {
            if counter.exceeded {
                return Err(ArchiveInspectError::EntryTooLarge(path));
            }
            return Err(ArchiveInspectError::Io(error));
        }

        total_uncompressed_bytes = total_uncompressed_bytes
            .checked_add(counter.bytes)
            .ok_or(ArchiveInspectError::TotalTooLarge)?;
        if total_uncompressed_bytes > limits.max_total_uncompressed_bytes {
            return Err(ArchiveInspectError::TotalTooLarge);
        }

        entries.push(ArchiveEntryInfo {
            path,
            size: counter.bytes,
        });
    }

    Ok(ArchiveManifest {
        archive_bytes,
        total_uncompressed_bytes,
        entries,
    })
}

/// Confirm the engine byte expected for VX Ace. Kept public for the detector
/// and diagnostics layer; the full archive parser still validates the header.
pub fn is_rgss3a_header(header: &[u8]) -> bool {
    header.len() >= 8 && &header[..7] == RGSS_MAGIC && header[7] == VX_ACE_ENGINE_BYTE
}

/// Expose the engine enum selected by the pinned archive library without
/// allowing callers to accidentally select XP/VX for a VX Ace archive.
pub fn vxace_engine() -> Engine {
    Engine::Vxace
}
