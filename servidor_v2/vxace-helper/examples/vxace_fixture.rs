//! CI-only fixture generator and inspector. Never runs Game.exe/RGSS301.dll.
use marshal_rs::{dump, load};
use rpgmad_lib::{decrypt_from_reader, encrypt_to_writer, Engine, EntrySource};
use rvpacker_txt_rs_lib::{core::Base, types::Scripts};
use std::{env, fs::{self,File}, io::{self, BufWriter, Cursor, Read, Write}, path::Path};

const LARGE_ENTRY_SIZE: usize = 240*1024*1024;
const LARGE_ENTRIES: usize = 5;

// Generate valid encrypted fixture payloads lazily, not a 1.2 GiB Vec.
struct GeneratedEntry {
    path: Vec<u8>,
    data: Vec<u8>,
    padding: usize,
    fill: u8,
}
impl EntrySource for GeneratedEntry {
    fn path(&self) -> &[u8] { &self.path }
    fn size(&self) -> usize { self.data.len()+self.padding }
    fn open(&self) -> io::Result<impl Read> {
        Ok(Cursor::new(self.data.clone()).chain(io::repeat(self.fill).take(self.padding as u64)))
    }
}
fn generated(path: &[u8], data: &[u8]) -> GeneratedEntry {
    GeneratedEntry { path:path.to_vec(), data:data.to_vec(), padding:0, fill:0 }
}

// Reproduce the user's reported entry index, with both UTF-8 and legacy
// byte-encoded names in the same archive. No commercial assets are used.
fn encoding_entries() -> Vec<GeneratedEntry> {
    let mut result = Vec::new();
    for n in 4..307 {
        result.push(generated(format!("Graphics\\qa-encoding-{n:03}.bin").as_bytes(),b"index fixture"));
    }
    for name in [
        b"Graphics\\Caf\xe9.png".as_slice(),
        "Graphics\\雪☃.png".as_bytes(),
        b"Graphics\\\x83\x5c\\asset.png",
        b"Graphics\\legacy-\xff.bin",
    ] {
        result.push(generated(name,b"multilingual resource preserved"));
    }
    result
}

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
        assert!(mode=="packed" || mode=="packed-large");
        let mut entries=vec![
            generated(b"Data\\Scripts.rvdata2",&script),
            generated(b"Data\\System.rvdata2",other),
            generated(b"Data\\MapInfos.rvdata2",other),
            generated(b"Graphics\\keep.png",b"untouched fixture"),
        ];
        entries.extend(encoding_entries());
        assert_eq!(entries[307].path,b"Graphics\\Caf\xe9.png");
        if mode=="packed-large" {
            for i in 0..LARGE_ENTRIES {
                entries.push(GeneratedEntry {
                    path:format!("Graphics\\qa-large-{i:02}.bin").into_bytes(),
                    data:Vec::new(), padding:LARGE_ENTRY_SIZE, fill:0x31+i as u8,
                });
            }
        }
        let file=File::create(root.join("Game.rgss3a")).unwrap();
        let mut output=BufWriter::new(file);
        encrypt_to_writer(&entries,Engine::Vxace,&mut output).unwrap();
        output.flush().unwrap();
        output.into_inner().unwrap().sync_all().unwrap();
        let size=fs::metadata(root.join("Game.rgss3a")).unwrap().len();
        if mode=="packed-large" {
            assert!(size>=1_216_546*1024,"large archive fixture is too small");
            println!("IA_VXACE_LARGE_FIXTURE_BYTES={size}");
        }
    }
    fs::write(root.join("Save01.rvdata2"),b"unchanged save fixture").unwrap();
}
fn verify(root:&Path,plugin:&Path) {
    let path=root.join("Game.rgss3a");
    let bytes=if path.exists() {
        let large=fs::metadata(&path).unwrap().len()>900*1024*1024;
        let mut archive=decrypt_from_reader(File::open(path).unwrap()).unwrap();
        let mut bytes=Vec::new();
        let mut seen=[false;LARGE_ENTRIES];
        let mixed=encoding_entries();
        let mut kept=false;
        for (n,expected) in mixed.iter().enumerate() {
            let i=n+4;
            assert_eq!(archive.path(i),expected.path.as_slice(),"encoded name bytes changed");
            let mut payload=Vec::new();
            archive.read_entry(i).unwrap().take(128).read_to_end(&mut payload).unwrap();
            assert_eq!(payload,expected.data,"encoded-name payload changed");
        }
        println!("IA_VXACE_MIXED_ENCODING_ENTRY_307_AND_PAYLOADS_PASS");
        for i in 0..archive.entry_count() {
            let name=archive.path(i).to_vec();
            if name.eq_ignore_ascii_case(b"Data\\Scripts.rvdata2") {
                assert!(bytes.is_empty());
                archive.read_entry(i).unwrap().read_to_end(&mut bytes).unwrap();
            } else if name.eq_ignore_ascii_case(b"Graphics\\keep.png") {
                let mut keep=Vec::new();
                archive.read_entry(i).unwrap().take(100).read_to_end(&mut keep).unwrap();
                assert_eq!(keep,b"untouched fixture");
                kept=true;
            } else {
                for (n, found) in seen.iter_mut().enumerate() {
                    if name==format!("Graphics\\qa-large-{n:02}.bin").as_bytes() {
                        assert!(!*found);
                        let mut input=archive.read_entry(i).unwrap();
                        let mut buffer=vec![0u8;256*1024];
                        let mut total=0usize;
                        loop {
                            let count=input.read(&mut buffer).unwrap();
                            if count==0 { break; }
                            assert!(buffer[..count].iter().all(|b| *b==0x31+n as u8),"large payload changed");
                            total+=count;
                        }
                        assert_eq!(total,LARGE_ENTRY_SIZE,"large payload length changed");
                        *found=true;
                        break;
                    }
                }
            }
        }
        assert!(kept);
        assert_eq!(archive.entry_count(),4+mixed.len()+if large { LARGE_ENTRIES } else { 0 });
        assert_eq!(seen.iter().filter(|value| **value).count(),if large { LARGE_ENTRIES } else { 0 });
        if large { println!("IA_VXACE_LARGE_NON_SCRIPT_PAYLOADS_PRESERVED_PASS"); }
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
