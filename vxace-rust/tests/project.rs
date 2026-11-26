use marshal_rs::{arena::{Arena, ValueId}, dump};
use rvpacker_txt_rs_lib::{core::Base, types::Scripts, FileFlags};
use std::{fs, path::Path};
use tempfile::tempdir;
use vxace_rgss3_core::project::{
    all_vxace_file_flags, apply_project_translation, extract_project_text, ProjectTextError,
};

fn japanese_scripts_file() -> Vec<u8> {
    let scripts = Scripts::new(
        vec![303],
        vec!["$game_message.add('こんにちは')\\n".to_owned()],
        vec!["Japanese".to_owned()],
    );
    dump(&Base::encode_scripts(&scripts))
}

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

    let source_text = fs::read_to_string(&translation_file).expect("read Unicode translation");
    let translated_text = source_text.replace("Hello world<#>", "Hello world<#>Hola mundo");
    fs::write(&translation_file, translated_text).expect("write Unicode translation");

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


fn ruby_object(
    arena: &mut Arena<'static>,
    class: &str,
    fields: &[(&str, ValueId)],
) -> ValueId {
    let ivars = fields
        .iter()
        .map(|(name, value)| (format!("@{name}").into_bytes(), *value))
        .collect::<Vec<_>>();
    arena
        .push_object(class.as_bytes().to_vec(), &ivars)
        .expect("build Ruby object fixture")
}

fn actors_file() -> Vec<u8> {
    let mut arena = Arena::builder();
    let id = arena.push_fixnum(1);
    let name = arena.push_string("Actor One".to_owned());
    let nickname = arena.push_string("勇者".to_owned());
    let actor = arena
        .push_object(
            b"Object".to_vec(),
            &[
                (b"id".to_vec(), id),
                (b"name".to_vec(), name),
                (b"nickname".to_vec(), nickname),
            ],
        )
        .expect("build actor fixture");
    let nil = arena.push_nil();
    let root = arena.push_array(&[nil, actor]).expect("build actors array");
    assert!(arena.set_root(root));
    dump(&arena)
}

fn system_file() -> Vec<u8> {
    let mut arena = Arena::builder();

    let armor = arena.push_string("Light Armor".to_owned());
    let armor_types = arena.push_array(&[armor]).expect("build armor types");
    let element = arena.push_string("Fire".to_owned());
    let elements = arena.push_array(&[element]).expect("build elements");
    let skill = arena.push_string("Magic".to_owned());
    let skill_types = arena.push_array(&[skill]).expect("build skill types");
    let weapon = arena.push_string("Sword".to_owned());
    let weapon_types = arena.push_array(&[weapon]).expect("build weapon types");
    let equip = arena.push_string("Accessory".to_owned());
    let equip_types = arena.push_array(&[equip]).expect("build equip types");

    let message_key = arena.push_string("battle_start".to_owned());
    let message_value = arena.push_string("Ready for battle!".to_owned());
    let messages = arena
        .push_hash(&[(message_key, message_value)], None)
        .expect("build system messages");
    let terms = ruby_object(&mut arena, "RPG::System::Terms", &[("messages", messages)]);

    let currency_unit = arena.push_string("Gold".to_owned());
    let game_title = arena.push_string("サンプルゲーム".to_owned());
    let system = ruby_object(
        &mut arena,
        "RPG::System",
        &[
            ("armor_types", armor_types),
            ("elements", elements),
            ("skill_types", skill_types),
            ("weapon_types", weapon_types),
            ("equip_types", equip_types),
            ("terms", terms),
            ("currency_unit", currency_unit),
            ("game_title", game_title),
        ],
    );
    assert!(arena.set_root(system));
    dump(&arena)
}

fn mapinfos_file() -> Vec<u8> {
    let mut arena = Arena::builder();
    let name = arena.push_string("Town".to_owned());
    let order = arena.push_fixnum(1);
    let parent_id = arena.push_fixnum(0);
    let info = ruby_object(
        &mut arena,
        "RPG::MapInfo",
        &[("name", name), ("order", order), ("parent_id", parent_id)],
    );
    let map_id = arena.push_fixnum(1);
    let root = arena
        .push_hash(&[(map_id, info)], None)
        .expect("build MapInfos hash");
    assert!(arena.set_root(root));
    dump(&arena)
}

fn map_file() -> Vec<u8> {
    let mut arena = Arena::builder();

    let message = arena.push_string("こんにちは、世界！".to_owned());
    let parameters = arena.push_array(&[message]).expect("build message parameters");
    let message_code = arena.push_fixnum(401);
    let indent = arena.push_fixnum(0);
    let command = ruby_object(
        &mut arena,
        "RPG::EventCommand",
        &[
            ("code", message_code),
            ("indent", indent),
            ("parameters", parameters),
        ],
    );

    let end_code = arena.push_fixnum(0);
    let end_indent = arena.push_fixnum(0);
    let end_parameters = arena.push_array(&[]).expect("build end parameters");
    let end = ruby_object(
        &mut arena,
        "RPG::EventCommand",
        &[
            ("code", end_code),
            ("indent", end_indent),
            ("parameters", end_parameters),
        ],
    );

    let list = arena.push_array(&[command, end]).expect("build event list");
    let page = ruby_object(&mut arena, "RPG::Event::Page", &[("list", list)]);
    let pages = arena.push_array(&[page]).expect("build event pages");
    let event_id = arena.push_fixnum(1);
    let event_name = arena.push_string("Greeting".to_owned());
    let x = arena.push_fixnum(1);
    let y = arena.push_fixnum(1);
    let event = ruby_object(
        &mut arena,
        "RPG::Event",
        &[
            ("id", event_id),
            ("name", event_name),
            ("x", x),
            ("y", y),
            ("pages", pages),
        ],
    );

    let event_key = arena.push_fixnum(1);
    let events = arena
        .push_hash(&[(event_key, event)], None)
        .expect("build map events");
    let display_name = arena.push_string("Town".to_owned());
    let map = ruby_object(
        &mut arena,
        "RPG::Map",
        &[("display_name", display_name), ("events", events)],
    );
    assert!(arena.set_root(map));
    dump(&arena)
}

fn replace_translation(path: &Path, source: &str, translated: &str) {
    let text = fs::read_to_string(path).expect("read translation document");
    let source_line = format!("{source}<#>");
    assert!(
        text.contains(&source_line),
        "expected {source_line:?} in {}:\n{text}",
        path.display(),
    );
    fs::write(
        path,
        text.replace(&source_line, &format!("{source}<#>{translated}")),
    )
    .expect("write translated document");
}

fn contains_bytes(bytes: &[u8], needle: &str) -> bool {
    bytes
        .windows(needle.len())
        .any(|window| window == needle.as_bytes())
}

#[test]
fn all_vxace_file_groups_round_trip_through_an_isolated_workspace() {
    let temp = tempdir().expect("temporary test root");
    let data_dir = temp.path().join("Game").join("Data");
    fs::create_dir_all(&data_dir).expect("create Data directory");

    let originals = [
        ("Actors.rvdata2", actors_file()),
        ("MapInfos.rvdata2", mapinfos_file()),
        ("Map001.rvdata2", map_file()),
        ("System.rvdata2", system_file()),
        ("Scripts.rvdata2", japanese_scripts_file()),
    ];
    for (name, bytes) in &originals {
        fs::write(data_dir.join(name), bytes).expect("write synthetic VX Ace file");
    }

    let translation_dir = temp.path().join("translation-workspace");
    extract_project_text(&data_dir, &translation_dir, all_vxace_file_flags())
        .expect("extract map, database, system and script text");

    replace_translation(
        &translation_dir.join("maps.txt"),
        "こんにちは、世界！",
        "Hola mapa",
    );
    replace_translation(
        &translation_dir.join("actors.txt"),
        "勇者",
        "Héroe",
    );
    replace_translation(
        &translation_dir.join("system.txt"),
        "サンプルゲーム",
        "Juego de prueba",
    );
    replace_translation(
        &translation_dir.join("scripts.txt"),
        "Hello world",
        "Hola script",
    );

    let translation_snapshots = [
        "maps.txt",
        "actors.txt",
        "system.txt",
        "scripts.txt",
    ]
    .map(|name| {
        (
            name,
            fs::read(translation_dir.join(name)).expect("snapshot translation document"),
        )
    });

    let output_dir = temp.path().join("translated-build");
    apply_project_translation(&data_dir, &translation_dir, &output_dir, all_vxace_file_flags())
        .expect("rebuild all selected VX Ace file groups");

    let output_data = output_dir.join("Data");
    for name in [
        "Actors.rvdata2",
        "Map001.rvdata2",
        "System.rvdata2",
        "Scripts.rvdata2",
    ] {
        assert!(output_data.join(name).is_file(), "missing output {name}");
    }

    assert!(
        contains_bytes(
            &fs::read(output_data.join("Actors.rvdata2")).expect("read actors output"),
            "Héroe",
        ),
        "database nickname translation was not written",
    );
    assert!(
        contains_bytes(
            &fs::read(output_data.join("Map001.rvdata2")).expect("read map output"),
            "Hola mapa",
        ),
        "map event translation was not written",
    );
    assert!(
        contains_bytes(
            &fs::read(output_data.join("System.rvdata2")).expect("read system output"),
            "Juego de prueba",
        ),
        "system title translation was not written",
    );

    let scripts = fs::read(output_data.join("Scripts.rvdata2")).expect("read scripts output");
    let arena = marshal_rs::load(&scripts)
        .expect("load translated scripts Marshal")
        .into_owned();
    let decoded = rvpacker_txt_rs_lib::core::Base::decode_scripts(&arena, arena.root(), None)
        .expect("decode translated scripts");
    assert!(
        decoded.contents.iter().any(|source| source.contains("Hola script")),
        "script translation was not written",
    );

    for (name, original) in &originals {
        assert_eq!(
            fs::read(data_dir.join(name)).expect("read source after build"),
            *original,
            "source file {name} was modified",
        );
    }
    for (name, original) in translation_snapshots {
        assert_eq!(
            fs::read(translation_dir.join(name)).expect("read translation after build"),
            original,
            "translation document {name} was modified",
        );
    }
}
