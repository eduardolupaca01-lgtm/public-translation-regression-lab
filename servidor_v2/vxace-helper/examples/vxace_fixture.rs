//! CI-only fixture generator and inspector. Never runs Game.exe/RGSS301.dll.
use marshal_rs::{dump, load};
use rpgmad_lib::{decrypt_from_reader, encrypt_to_vec, ArchiveEntry, Engine};
use rvpacker_txt_rs_lib::{core::Base, types::Scripts};
use std::{env, fs::{self,File}, io::Read, path::Path};

fn original() -> Scripts {
    Scripts::new(vec![101,202], vec!["# synthetic title\n".to_owned(),"# synthetic main\n".to_owned()],
        vec!["Scene_Title".to_owned(),"Main".to_owned()])
}
fn pe() -> Vec<u8> {
    let mut b=vec![0;128];
    b[..2].copy_from_slice(b"MZ");
    b[60]=64;
    b[64..70].copy_from_slice(b"PE\0\0\x4c\x01");
    b
}
fn make(root:&Path,mode:&str) {
    fs::create_dir(root).unwrap();
    fs::create_dir(root.join("System")).unwrap();
    fs::write(root.join("Game.exe"),pe()).unwrap();
    fs::write(root.join("System/RGSS301.dll"),pe()).unwrap();
    fs::write(root.join("Game.ini"),"[Game]\nLibrary=System\\RGSS301.dll\nScripts=Data\\Scripts.rvdata2\nRTP=\nTitle=QA VX Ace\n").unwrap();
    let script=dump(&Base::encode_scripts(&original()));
    let other=b"\x04\x08\x30";
    if mode=="loose" {
        fs::create_dir(root.join("Data")).unwrap();
        fs::write(root.join("Data/Scripts.rvdata2"),script).unwrap();
        for name in ["System.rvdata2","MapInfos.rvdata2"] {fs::write(root.join("Data").join(name),other).unwrap();}
    } else {
        assert_eq!(mode,"packed");
        let entries=[
            ArchiveEntry{path:b"Data\\Scripts.rvdata2",data:&script},
            ArchiveEntry{path:b"Data\\System.rvdata2",data:other},
            ArchiveEntry{path:b"Data\\MapInfos.rvdata2",data:other},
            ArchiveEntry{path:b"Graphics\\keep.png",data:b"untouched fixture"},
        ];
        fs::write(root.join("Game.rgss3a"),encrypt_to_vec(&entries,Engine::Vxace).unwrap()).unwrap();
    }
    fs::write(root.join("Save01.rvdata2"),b"unchanged save fixture").unwrap();
}
fn verify(root:&Path,plugin:&Path) {
    let path=root.join("Game.rgss3a");
    let bytes=if path.exists() {
        let mut archive=decrypt_from_reader(File::open(path).unwrap()).unwrap();
        let mut bytes=Vec::new();
        for i in 0..archive.entry_count() {
            if archive.path(i).eq_ignore_ascii_case(b"Data\\Scripts.rvdata2") {
                archive.read_entry(i).unwrap().read_to_end(&mut bytes).unwrap();
            }
        }
        bytes
    } else {fs::read(root.join("Data/Scripts.rvdata2")).unwrap()};
    let arena=load(&bytes).unwrap().into_owned();
    let mut scripts=Base::decode_scripts(&arena,arena.root(),None).unwrap();
    assert_eq!(scripts.names.iter().filter(|s|s.as_str()=="IA Traductora RGSS3").count(),1);
    let index=scripts.names.iter().position(|s|s=="IA Traductora RGSS3").unwrap();
    assert_eq!(index+1,scripts.names.iter().position(|s|s=="Main").unwrap());
    assert_eq!(scripts.contents[index],fs::read_to_string(plugin).unwrap());
    scripts.names.remove(index);scripts.numbers.remove(index);scripts.contents.remove(index);
    let before=original();
    assert_eq!(scripts.names,before.names);
    assert_eq!(scripts.numbers,before.numbers);
    assert_eq!(scripts.contents,before.contents);
    println!("IA_VXACE_INSTALLED_SCRIPT_IDENTITY_PASS");
}
fn main(){
    let a:Vec<String>=env::args().collect();
    assert_eq!(a.len(),4);
    match a[1].as_str() {
        "create"=>make(Path::new(&a[2]),&a[3]),
        "verify"=>verify(Path::new(&a[2]),Path::new(&a[3])),
        _=>panic!("invalid fixture command"),
    }
}
