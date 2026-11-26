//! VX Ace text extraction and application for the RGSS3 Marshal scripts file.
//!
//! The archive layer handles RGSS3A containers. This module handles the inner
//! Scripts.rvdata2 Marshal/Zlib structure through a pinned, independently
//! maintained parser. All operations are in-memory: the caller's source slice
//! is never written or mutated.

use rvpacker_txt_rs_lib::{core::Base, EngineType, Mode};
use thiserror::Error;

/// Maximum accepted Scripts.rvdata2 input. The archive reader has a matching
/// per-entry ceiling; this check also protects direct callers of this module.
pub const MAX_SCRIPTS_FILE_BYTES: usize = 512 * 1024 * 1024;

/// Maximum accepted UTF-8 translation document size.
pub const MAX_SCRIPT_TRANSLATION_BYTES: usize = 128 * 1024 * 1024;

#[derive(Debug, Error)]
pub enum ScriptTextError {
    #[error("Scripts.rvdata2 is {actual} bytes; the limit is {limit}")]
    InputTooLarge { actual: usize, limit: usize },
    #[error("script translation document is {actual} bytes; the limit is {limit}")]
    TranslationTooLarge { actual: usize, limit: usize },
    #[error("VX Ace Marshal script processing failed: {0}")]
    Processing(#[from] rvpacker_txt_rs_lib::Error),
    #[error("the script extractor returned a non-UTF-8 translation document")]
    OutputNotUtf8(#[from] std::string::FromUtf8Error),
}

/// Extracts translatable Ruby string literals from a VX Ace Scripts.rvdata2.
///
/// The returned text is a translation document understood by
/// apply_scripts_translation. Empty script arrays produce an empty string.
/// No file is created and script_data is never modified.
pub fn extract_scripts_text(script_data: &[u8]) -> Result<String, ScriptTextError> {
    if script_data.len() > MAX_SCRIPTS_FILE_BYTES {
        return Err(ScriptTextError::InputTooLarge {
            actual: script_data.len(),
            limit: MAX_SCRIPTS_FILE_BYTES,
        });
    }

    let mut base = Base::new(Mode::read(), EngineType::VXAce);
    match base.process_scripts(script_data, None)? {
        Some(processed) => Ok(String::from_utf8(processed.as_ref().to_vec())?),
        None => Ok(String::new()),
    }
}

/// Applies a translation document to a VX Ace Scripts.rvdata2 and returns a
/// new Marshal byte stream. The input bytes remain untouched.
///
/// None means the source contained no scripts that the processor could write.
/// A returned Some is a new serialized file; callers should publish it only
/// through the separate transactional installation layer.
pub fn apply_scripts_translation(
    script_data: &[u8],
    translation: &str,
) -> Result<Option<Vec<u8>>, ScriptTextError> {
    if script_data.len() > MAX_SCRIPTS_FILE_BYTES {
        return Err(ScriptTextError::InputTooLarge {
            actual: script_data.len(),
            limit: MAX_SCRIPTS_FILE_BYTES,
        });
    }
    if translation.len() > MAX_SCRIPT_TRANSLATION_BYTES {
        return Err(ScriptTextError::TranslationTooLarge {
            actual: translation.len(),
            limit: MAX_SCRIPT_TRANSLATION_BYTES,
        });
    }

    let mut base = Base::new(Mode::Write, EngineType::VXAce);
    let processed = base.process_scripts(script_data, Some(translation))?;
    Ok(processed.map(|data| data.as_ref().to_vec()))
}
