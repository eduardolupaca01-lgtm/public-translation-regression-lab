//! Test-only child process. Never packaged with the product.
use std::{env, fs, path::PathBuf};

fn main() {
    let args: Vec<_> = env::args_os().collect();
    assert_eq!(args.len(), 7);
    assert_eq!(args[1], "--game-root");
    assert_eq!(args[3], "--parent-pid");
    assert_eq!(args[5], "--diagnostic-file");
    let root = PathBuf::from(&args[2]);
    assert_eq!(env::current_dir().unwrap().canonicalize().unwrap(), root.canonicalize().unwrap());
    assert!(root.join("Game.exe").is_file());
    assert!(root.join("System/RGSS301.dll").is_file());
    let parent: u32 = args[4].to_str().unwrap().parse().unwrap();
    assert!(parent > 0);
    let expected = root.join("IA Traductora/.local/Rpg")
        .join(format!("vxace-startup-worker-{parent}.json"));
    let diagnostic = PathBuf::from(&args[6]);
    assert_eq!(diagnostic.canonicalize().unwrap(), expected.canonicalize().unwrap());
    fs::write(diagnostic, b"{\"schema\":\"ia-traductora-startup-v1\",\"code\":\"IA_VXACE_PROBE_READY\"}\n").unwrap();
}
