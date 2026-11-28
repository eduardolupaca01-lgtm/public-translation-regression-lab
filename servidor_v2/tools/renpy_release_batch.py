"""Enumerate every official release in bounded batches; never claim certification."""
import argparse
import json
from pathlib import Path

CATALOG=Path(__file__).resolve().parents[1]/"cmd/servidor/renpy_assets/releases.txt"
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--family",choices=["4","5","6","7","8","all"],default="all")
    p.add_argument("--offset",type=int,default=0)
    p.add_argument("--limit",type=int,default=12)
    args=p.parse_args()
    versions=[x.strip() for x in CATALOG.read_text(encoding="ascii").splitlines() if x.strip() and not x.startswith("#")]
    if len(versions)!=188 or len(set(versions))!=188:raise SystemExit("IA_RENPY_CATALOGO_INVALIDO")
    if args.family!="all":versions=[x for x in versions if x.startswith(args.family)]
    if args.offset<0 or not 1<=args.limit<=20:raise SystemExit("IA_RENPY_LOTE_INVALIDO")
    print(json.dumps({"total":len(versions),"offset":args.offset,"include":[{"version":v,"status":"pending_exact_runtime","official_index":"https://www.renpy.org/release_list.html"} for v in versions[args.offset:args.offset+args.limit]]},indent=2))
if __name__=="__main__":main()
