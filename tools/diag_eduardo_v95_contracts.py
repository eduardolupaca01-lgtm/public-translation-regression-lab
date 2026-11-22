"""Read-only, no-source-leak diagnosis of the original V95 gate 06.

All private test output remains on the temporary Windows runner. The public
job receives only an allowlisted test label and exit status.
"""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

CHECKS = [
 ("TX718_BOUNDED_SCANNER", ["-m","unittest","discover","-s","tests","-p","test_tx718_original_v95_bounded_scan_recovery.py","-v"]),
 ("TX759_TEMPORAL", ["-m","unittest","discover","-s","tests","-p","test_tx759_v95_temporal_semantic_guard.py","-v"]),
 ("TX760_REPACK", ["-m","unittest","discover","-s","tests","-p","test_tx718_repack_tx760_attestation.py","-v"]),
 ("TX471_FREEZE", ["-m","unittest","discover","-s","tests","-p","test_tx471_freeze_original_v95_worker.py","-v"]),
 ("TX760_SOURCE_SELFTEST", ["-m","tools.tx760_v95_japanese_sentence_integrity","--self-test-archive","audit/private-quarantine/tx203-private-source.zip"]),
 ("TX718_UNICODE", ["-m","unittest","discover","-s","tests","-p","test_tx718_unicode_diagnostics.py","-v"]),
]

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("--source-root", type=Path, required=True)
 parser.add_argument("--runner-temp", type=Path, required=True)
 args=parser.parse_args()
 root=args.source_root.resolve()
 if not (root/"audit/private-quarantine/tx203-private-source.zip").is_file():
  print("EDUARDO_ARCHIVED_SOURCE_MISSING")
  return 1
 for number,(label,command) in enumerate(CHECKS,1):
  log=args.runner_temp/f"private-diagnostic-{number:02d}.log"
  with log.open("wb") as sink:
   process=subprocess.run([sys.executable,*command],cwd=root,stdout=sink,
                          stderr=subprocess.STDOUT,check=False,timeout=180)
  print("EDUARDO_PRIVATE_SOURCE_CHECK:"+label+":"+
        ("PASS" if process.returncode==0 else "FAIL"),flush=True)
  if process.returncode!=0:
   return 1
 return 0

if __name__ == "__main__":
 raise SystemExit(main())
