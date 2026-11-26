use marshal_rs::dump;
use rvpacker_txt_rs_lib::{core::Base, types::Scripts, FileFlags};
use std::fs;
use tempfile::tempdir;
use vxace_rgss3_core::project::{
    all_vxace_file_flags, apply_project_translation, extract_project_text, ProjectTextError,
};

fn scripts_file() -> Vec<u8> {
    let scripts = Scripts::new(
        vec![101],
        vec!["$game_message.add('Hello world')\n".to_owned()],
        vec!["Main".to_owned()],
    );
    dump(&Base::encode_scripts(&scripts))
}

#[test]
fn directory_extraction_writes_translation_workspace_without_touching_source() {
    let temp = tempdir().expect("temporary test root");
    let data_dir = temp.path().join("Game").join("Data");
    fs::create_dir_all(&data_dir).expect("create Data directory");
    let source_file = data_dir.join("Scripts.rvdata2");
    let original = scripts_file();
    fs::write(&source_file, &original).expect("write synthetic game script");

    let translation_dir = temp.path().join("translation-workspace");
    extract_project_text(&data_dir, &translation_dir, FileFlags::Scripts)
        .expect("extract script translations");

    let translation = fs::read_to_string(translation_dir.join("scripts.txt"))
        .expect("translation file should be created");
    assert!(translation.contains("Hello world<#>"));
    assert_eq!(fs::read(&source_file).expect("read source"), original);
}

#[test]
fn directory_write_builds_a_separate_data_tree() {
    let temp = tempdir().expect("temporary test root");
    let data_dir = temp.path().join("Game").join("Data");
    fs::create_dir_all(&data_dir).expect("create Data directory");
    let source_file = data_dir.join("Scripts.rvdata2");
    let original = scripts_file();
    fs::write(&source_file, &original).expect("write synthetic game script");

    let translation_dir = temp.path().join("translation-workspace");
    extract_project_text(&data_dir, &translation_dir, FileFlags::Scripts)
        .expect("extract script translations");
    let translation_file = translation_dir.join("scripts.txt");
    let source_text = fs::read_to_string(&translation_file).expect("read translation");
    let translated_text = source_text.replace("Hello world<#>", "Hello world<#>Hola mundo");
    fs::write(&translation_file, translated_text).expect("write translated text");

    let output_dir = temp.path().join("translated-build");
    apply_project_translation(&data_dir, &translation_dir, &output_dir, FileFlags::Scripts)
        .expect("build translated Data tree");

    let output_file = output_dir.join("Data").join("Scripts.rvdata2");
    assert!(output_file.is_file(), "rebuilt Scripts.rvdata2 should exist");
    assert_ne!(fs::read(&output_file).expect("read output"), original);
    assert_eq!(fs::read(&source_file).expect("read original source"), original);
    assert!(translation_file.is_file(), "translation workspace should remain intact");
}

#[test]
fn refuses_to_create_a_translation_workspace_inside_the_source_data_tree() {
    let temp = tempdir().expect("temporary test root");
    let data_dir = temp.path().join("Game").join("Data");
    fs::create_dir_all(&data_dir).expect("create Data directory");
    fs::write(data_dir.join("Scripts.rvdata2"), scripts_file()).expect("write fixture");

    let nested_workspace = data_dir.join("translation-workspace");
    let result = extract_project_text(&data_dir, &nested_workspace, FileFlags::Scripts);

    assert!(matches!(
        result,
        Err(ProjectTextError::WorkspaceOverlapsSource { .. })
    ));
    assert!(!nested_workspace.exists(), "rejected workspace must not be created");
}

#[test]
fn default_flags_cover_maps_database_system_and_scripts() {
    let flags = all_vxace_file_flags();
    assert!(flags.contains(FileFlags::Map));
    assert!(flags.contains(FileFlags::other()));
    assert!(flags.contains(FileFlags::System));
    assert!(flags.contains(FileFlags::Scripts));
}
