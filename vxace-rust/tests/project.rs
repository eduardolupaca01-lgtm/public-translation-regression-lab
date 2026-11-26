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


#[test]
fn failed_directory_write_does_not_publish_partial_data() {
    let temp = tempdir().expect("temporary test root");
    let data_dir = temp.path().join("Game").join("Data");
    fs::create_dir_all(&data_dir).expect("create Data directory");
    let source_file = data_dir.join("Scripts.rvdata2");
    fs::write(&source_file, scripts_file()).expect("write valid script fixture");

    let translation_dir = temp.path().join("translation-workspace");
    extract_project_text(&data_dir, &translation_dir, FileFlags::Scripts)
        .expect("extract a valid translation workspace");
    let translation_file = translation_dir.join("scripts.txt");
    let translation_before = fs::read(&translation_file).expect("snapshot translation file");

    // Force a real processing error after the staged output directory exists.
    fs::write(&source_file, b"not a Ruby Marshal stream")
        .expect("replace source with invalid fixture");
    let source_before = fs::read(&source_file).expect("snapshot invalid source");
    let output_dir = temp.path().join("translated-build");

    let result = apply_project_translation(
        &data_dir,
        &translation_dir,
        &output_dir,
        FileFlags::Scripts,
    );

    assert!(result.is_err(), "invalid Marshal source must fail the build");
    assert!(!output_dir.exists(), "failed build must not publish a partial output");
    assert_eq!(fs::read(&source_file).expect("read source after failure"), source_before);
    assert_eq!(
        fs::read(&translation_file).expect("read translation after failure"),
        translation_before,
    );
}

#[test]
fn directory_write_refuses_to_overwrite_an_existing_output() {
    let temp = tempdir().expect("temporary test root");
    let data_dir = temp.path().join("Game").join("Data");
    fs::create_dir_all(&data_dir).expect("create Data directory");
    fs::write(data_dir.join("Scripts.rvdata2"), scripts_file())
        .expect("write script fixture");

    let translation_dir = temp.path().join("translation-workspace");
    extract_project_text(&data_dir, &translation_dir, FileFlags::Scripts)
        .expect("extract translation workspace");

    let output_dir = temp.path().join("translated-build");
    fs::create_dir_all(&output_dir).expect("create pre-existing destination");
    let sentinel = output_dir.join("owner-file.txt");
    fs::write(&sentinel, b"do not overwrite").expect("write destination sentinel");

    let result = apply_project_translation(
        &data_dir,
        &translation_dir,
        &output_dir,
        FileFlags::Scripts,
    );

    assert!(matches!(
        result,
        Err(ProjectTextError::OutputAlreadyExists(_))
    ));
    assert_eq!(
        fs::read(&sentinel).expect("read destination sentinel"),
        b"do not overwrite",
    );
}

#[test]
fn directory_write_rejects_output_nested_inside_translation_workspace() {
    let temp = tempdir().expect("temporary test root");
    let data_dir = temp.path().join("Game").join("Data");
    fs::create_dir_all(&data_dir).expect("create Data directory");
    fs::write(data_dir.join("Scripts.rvdata2"), scripts_file())
        .expect("write script fixture");

    let translation_dir = temp.path().join("translation-workspace");
    extract_project_text(&data_dir, &translation_dir, FileFlags::Scripts)
        .expect("extract translation workspace");
    let output_dir = translation_dir.join("published-output");

    let result = apply_project_translation(
        &data_dir,
        &translation_dir,
        &output_dir,
        FileFlags::Scripts,
    );

    assert!(matches!(result, Err(ProjectTextError::WorkspacesOverlap { .. })));
    assert!(!output_dir.exists(), "overlapping output must not be created");
}

#[test]
fn project_workspaces_support_unicode_and_spaces() {
    let temp = tempdir().expect("temporary test root");
    let data_dir = temp
        .path()
        .join("Juego 日本語 con espacios")
        .join("Data");
    fs::create_dir_all(&data_dir).expect("create Unicode Data directory");
    let source_file = data_dir.join("Scripts.rvdata2");
    let original = scripts_file();
    fs::write(&source_file, &original).expect("write script fixture");

    let translation_dir = temp.path().join("traducción 日本語");
    extract_project_text(&data_dir, &translation_dir, FileFlags::Scripts)
        .expect("extract into Unicode workspace");
    let translation_file = translation_dir.join("scripts.txt");
    assert!(
        fs::read_to_string(&translation_file)
            .expect("read translation document")
            .contains("Hello world<#>"),
    );

    let output_dir = temp.path().join("salida traducida_日本語");
    apply_project_translation(&data_dir, &translation_dir, &output_dir, FileFlags::Scripts)
        .expect("publish Unicode output tree");
    assert!(
        output_dir.join("Data").join("Scripts.rvdata2").is_file(),
        "completed Data tree should be published",
    );
    assert_eq!(
        fs::read(&source_file).expect("read original source"),
        original,
        "Unicode path handling must not mutate the source game",
    );
}

#[test]
fn extraction_rejects_empty_file_flags_without_creating_a_workspace() {
    let temp = tempdir().expect("temporary test root");
    let data_dir = temp.path().join("Game").join("Data");
    fs::create_dir_all(&data_dir).expect("create Data directory");
    let translation_dir = temp.path().join("translation-workspace");

    let result = extract_project_text(&data_dir, &translation_dir, FileFlags::empty());

    assert!(matches!(result, Err(ProjectTextError::NoFileFlags)));
    assert!(!translation_dir.exists(), "invalid request must not create a workspace");
}
