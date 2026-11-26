//! Safe directory-level extraction and reconstruction for VX Ace Data files.
//!
//! The caller supplies an existing Data directory and separate translation /
//! output workspaces. This adapter delegates the per-file Marshal and text
//! formats to rvpacker-txt-rs-lib, while enforcing that no workspace overlaps
//! the source Data tree.

use rvpacker_txt_rs_lib::{EngineType, FileFlags, Mode, Processor};
use std::{
    ffi::OsString,
    fs,
    path::{Component, Path, PathBuf},
};
use tempfile::Builder as TempDirBuilder;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum ProjectTextError {
    #[error("source Data directory does not exist or is not a directory: {0}")]
    InvalidSourceDirectory(PathBuf),
    #[error("workspace overlaps the source Data directory: {workspace}")]
    WorkspaceOverlapsSource { workspace: PathBuf },
    #[error("translation and output workspaces overlap: {translation} and {output}")]
    WorkspacesOverlap {
        translation: PathBuf,
        output: PathBuf,
    },
    #[error("at least one VX Ace file kind must be selected")]
    NoFileFlags,
    #[error("output path must name a new directory: {0}")]
    InvalidOutputPath(PathBuf),
    #[error("output directory already exists: {0}")]
    OutputAlreadyExists(PathBuf),
    #[error("VX Ace processor did not create a staged Data directory")]
    MissingStagedData,
    #[error("workspace preparation failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("VX Ace project processing failed: {0}")]
    Processing(#[from] rvpacker_txt_rs_lib::Error),
}

/// All standard VX Ace text-bearing Data file groups supported by the
/// pinned processor: maps, database files, system terms and scripts.
#[must_use]
pub fn all_vxace_file_flags() -> FileFlags {
    FileFlags::Map | FileFlags::other() | FileFlags::System | FileFlags::Scripts
}

/// Extracts text from selected VX Ace Data files into a separate workspace.
///
/// The source Data directory is read-only. The translation workspace must be
/// disjoint from the source directory (and cannot be its parent).
pub fn extract_project_text(
    data_directory: impl AsRef<Path>,
    translation_directory: impl AsRef<Path>,
    file_flags: FileFlags,
) -> Result<(), ProjectTextError> {
    if file_flags.is_empty() {
        return Err(ProjectTextError::NoFileFlags);
    }

    let source = canonical_source(data_directory.as_ref())?;
    let translation = disjoint_workspace(&source, translation_directory.as_ref())?;
    fs::create_dir_all(&translation)?;
    let translation = translation.canonicalize()?;
    ensure_disjoint(&source, &translation)?;

    let mut processor = Processor {
        mode: Mode::read(),
        file_flags,
        ..Processor::default()
    };
    processor.process(EngineType::VXAce, &source, &translation, None)?;
    Ok(())
}

/// Applies an existing translation workspace into a separate output Data
/// tree. Neither the source Data directory nor the translation workspace is
/// modified by this adapter.
pub fn apply_project_translation(
    data_directory: impl AsRef<Path>,
    translation_directory: impl AsRef<Path>,
    output_directory: impl AsRef<Path>,
    file_flags: FileFlags,
) -> Result<(), ProjectTextError> {
    if file_flags.is_empty() {
        return Err(ProjectTextError::NoFileFlags);
    }

    let source = canonical_source(data_directory.as_ref())?;
    let translation = disjoint_workspace(&source, translation_directory.as_ref())?;
    let output = disjoint_workspace(&source, output_directory.as_ref())?;
    if translation == output
        || translation.starts_with(&output)
        || output.starts_with(&translation)
    {
        return Err(ProjectTextError::WorkspacesOverlap {
            translation,
            output,
        });
    }

    if !translation.is_dir() {
        return Err(ProjectTextError::InvalidSourceDirectory(translation));
    }
    let translation = translation.canonicalize()?;

    // Resolve the destination parent after creating it. This catches a parent
    // directory that is a symlink/reparse point into the source game.
    let output_name = output
        .file_name()
        .ok_or_else(|| ProjectTextError::InvalidOutputPath(output.clone()))?
        .to_os_string();
    let output_parent = output
        .parent()
        .ok_or_else(|| ProjectTextError::InvalidOutputPath(output.clone()))?;
    fs::create_dir_all(output_parent)?;
    let output_parent = output_parent.canonicalize()?;
    let output = output_parent.join(output_name);
    ensure_disjoint(&source, &output)?;

    if translation == output
        || translation.starts_with(&output)
        || output.starts_with(&translation)
    {
        return Err(ProjectTextError::WorkspacesOverlap {
            translation,
            output,
        });
    }
    if output.exists() {
        return Err(ProjectTextError::OutputAlreadyExists(output));
    }

    // Build under a temporary sibling directory. A failed Marshal parse,
    // translation read, or write drops the staging tree and never publishes a
    // partial Data directory at the caller's destination.
    let staging = TempDirBuilder::new()
        .prefix(".vxace-stage-")
        .tempdir_in(&output_parent)?;

    let mut processor = Processor {
        mode: Mode::Write,
        file_flags,
        ..Processor::default()
    };
    processor.process(EngineType::VXAce, &source, &translation, Some(staging.path()))?;

    let staged_data = staging.path().join("Data");
    if !staged_data.is_dir() {
        return Err(ProjectTextError::MissingStagedData);
    }

    // Claim the destination exclusively. Publishing Data with one same-volume
    // rename makes the completed tree visible at once and refuses an existing
    // destination instead of merging into or overwriting it.
    match fs::create_dir(&output) {
        Ok(()) => {}
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
            return Err(ProjectTextError::OutputAlreadyExists(output));
        }
        Err(error) => return Err(ProjectTextError::Io(error)),
    }

    let published_data = output.join("Data");
    if let Err(error) = fs::rename(&staged_data, &published_data) {
        // Remove only the empty destination directory created above. If an
        // external process placed content there, remove_dir will fail safely.
        let _ = fs::remove_dir(&output);
        return Err(ProjectTextError::Io(error));
    }

    Ok(())
}
fn canonical_source(path: &Path) -> Result<PathBuf, ProjectTextError> {
    let source = path.canonicalize()?;
    if !source.is_dir() {
        return Err(ProjectTextError::InvalidSourceDirectory(source));
    }
    Ok(source)
}

fn disjoint_workspace(
    source: &Path,
    workspace: &Path,
) -> Result<PathBuf, ProjectTextError> {
    let workspace = canonical_future_path(workspace)?;
    ensure_disjoint(source, &workspace)?;
    Ok(workspace)
}

fn ensure_disjoint(source: &Path, workspace: &Path) -> Result<(), ProjectTextError> {
    if workspace == source || workspace.starts_with(source) || source.starts_with(workspace) {
        return Err(ProjectTextError::WorkspaceOverlapsSource {
            workspace: workspace.to_path_buf(),
        });
    }
    Ok(())
}

/// Canonicalizes the existing prefix and appends not-yet-created components.
/// This catches paths that reach into the game through an existing symlink
/// without creating a destination before the overlap check.
fn canonical_future_path(path: &Path) -> Result<PathBuf, ProjectTextError> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()?.join(path)
    };

    let mut normalized = PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::Prefix(prefix) => normalized.push(prefix.as_os_str()),
            Component::RootDir => normalized.push(component.as_os_str()),
            Component::CurDir => {}
            Component::ParentDir => {
                normalized.pop();
            }
            Component::Normal(part) => normalized.push(part),
        }
    }

    let mut existing = normalized.clone();
    let mut missing: Vec<OsString> = Vec::new();
    while !existing.exists() {
        let name = existing
            .file_name()
            .ok_or_else(|| std::io::Error::new(std::io::ErrorKind::InvalidInput, "invalid workspace path"))?;
        missing.push(name.to_os_string());
        existing = existing
            .parent()
            .ok_or_else(|| std::io::Error::new(std::io::ErrorKind::InvalidInput, "workspace has no existing parent"))?
            .to_path_buf();
    }

    let mut canonical = existing.canonicalize()?;
    for component in missing.iter().rev() {
        canonical.push(component);
    }
    Ok(canonical)
}
