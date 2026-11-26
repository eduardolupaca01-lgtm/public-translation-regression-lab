use marshal_rs::{dump, load};
use rvpacker_txt_rs_lib::{core::Base, types::Scripts};
use vxace_rgss3_core::text::{
    apply_scripts_translation, extract_scripts_text, ScriptTextError,
};

fn scripts_file() -> Vec<u8> {
    let scripts = Scripts::new(
        vec![101, 202],
        vec![
            "$game_message.add('Hello world')\n".to_owned(),
            "$game_message.add('Keep this line')\n".to_owned(),
        ],
        vec!["Main".to_owned(), "Scene_Title".to_owned()],
    );

    dump(&Base::encode_scripts(&scripts))
}

fn decode_scripts(bytes: &[u8]) -> Scripts {
    let arena = load(bytes).expect("test fixture should be valid Marshal").into_owned();
    let root = arena.root();
    Base::decode_scripts(&arena, root, None).expect("test fixture should contain valid scripts")
}

#[test]
fn extracts_translatable_literals_from_vxace_scripts() {
    let original = scripts_file();
    let snapshot = original.clone();

    let translation = extract_scripts_text(&original).expect("script extraction should succeed");

    assert!(translation.contains("Hello world<#>"));
    assert!(translation.contains("Keep this line<#>"));
    assert_eq!(original, snapshot, "extraction must not mutate source bytes");
}

#[test]
fn applies_one_translation_and_preserves_other_script_entries() {
    let original = scripts_file();
    let before = decode_scripts(&original);
    let source = extract_scripts_text(&original).expect("script extraction should succeed");
    let translated = source.replace("Hello world<#>", "Hello world<#>Hola mundo");

    let patched = apply_scripts_translation(&original, &translated)
        .expect("translation application should succeed")
        .expect("the fixture has writable script entries");
    let after = decode_scripts(&patched);

    assert_eq!(before.numbers, after.numbers, "script magic numbers must stay in order");
    assert_eq!(before.names, after.names, "script names must stay in order");
    assert!(after.contents[0].contains("Hola mundo"));
    assert!(!after.contents[0].contains("Hello world"));
    assert!(after.contents[1].contains("Keep this line"));
}

#[test]
fn escapes_quotes_when_writing_a_ruby_string_literal() {
    let original = scripts_file();
    let source = extract_scripts_text(&original).expect("script extraction should succeed");
    let translated = source.replace("Hello world<#>", "Hello world<#>It's \"gold\"");

    let patched = apply_scripts_translation(&original, &translated)
        .expect("translation application should succeed")
        .expect("the fixture has writable script entries");
    let after = decode_scripts(&patched);

    assert!(after.contents[0].contains(r#"It\'s "gold""#));
    assert!(after.contents[1].contains("Keep this line"));
}

#[test]
fn rejects_invalid_marshal_input_without_touching_any_file() {
    let error = extract_scripts_text(b"not a Ruby Marshal stream")
        .expect_err("invalid Marshal input must be rejected");

    assert!(matches!(error, ScriptTextError::Processing(_)));
}
