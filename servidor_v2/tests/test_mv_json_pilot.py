"""Synthetic authored tests; never load third-party game scripts."""
import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"worker"))
import mv_json_pilot as p
from IATraductora import native_quality_reason,TranslationMemory

def fixture():
    rows=[
        {"code":101,"indent":0,"parameters":["portrait",0,0,2]},
        {"code":401,"indent":0,"parameters":[r"\C[2]Please open the wooden gate.\C[0]"]},
        {"code":401,"indent":0,"parameters":["橋を渡ってください。"]},
        {"code":401,"indent":0,"parameters":["Aster:"]},
        {"code":401,"indent":0,"parameters":[r"\CUSTOM[1]Please wait here."]},
        {"code":102,"indent":0,"parameters":[["Open the gate.","Wait here."],1,0,2,0]},
        {"code":402,"indent":0,"parameters":[0,"Open the gate."]},
        {"code":355,"indent":1,"parameters":["Please open the wooden gate."]},
        {"code":0,"indent":0,"parameters":[]},
    ]
    return {"events":[None,{"id":1,"name":"Aster","pages":[{"list":rows,"conditions":{"switch1Id":2}}]}],"width":20}

class MockNeural:
    def __init__(self):self.calls=[]
    def translate_many(self,lang,texts):
        self.calls.extend((lang,t) for t in texts)
        return [{"Please open the wooden gate.":"Abre la puerta de madera.","橋を渡ってください。":"Cruza el puente."}.get(t) for t in texts]

class PilotTests(unittest.TestCase):
    def test_only_native_display_lines_and_cache(self):
        original=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"IA Traductora"/".local"/"Rpg").mkdir(parents=True)
            memory=TranslationMemory(root)
            try:
                neural=MockNeural()
                doc=copy.deepcopy(original)
                stats=p.localize_map(doc,{"Aster"},lambda keys:p.resolve_local(keys,neural,memory,native_quality_reason),native_quality_reason)
                self.assertEqual(stats["translated_lines"],2)
                self.assertEqual(stats["new_translations"],2)
                expected=copy.deepcopy(original)
                rows=expected["events"][1]["pages"][0]["list"]
                rows[1]["parameters"][0]=r"\C[2]Abre la puerta de madera.\C[0]"
                rows[2]["parameters"][0]="Cruza el puente."
                self.assertEqual(doc,expected)
                again=copy.deepcopy(original);before=len(neural.calls)
                stats=p.localize_map(again,{"Aster"},lambda keys:p.resolve_local(keys,neural,memory,native_quality_reason),native_quality_reason)
                self.assertEqual(again,expected)
                self.assertEqual(stats["new_translations"],0)
                self.assertEqual(stats["cache_hits"],2)
                self.assertEqual(len(neural.calls),before)
            finally:memory.close()
    def test_reject_injected_control_and_preserve_original(self):
        doc=fixture();original=copy.deepcopy(doc)
        p.localize_map(doc,{"Aster"},lambda keys:({key:r"\V[1]Injected" for key in keys},{"new_translations":0,"cache_hits":0}),native_quality_reason)
        self.assertEqual(doc,original)
    def test_nested_choices_and_no_executable_labels(self):
        rows=[
            {"code":102,"indent":0,"parameters":[["Yes","No"],1,0,2,0]},
            {"code":402,"indent":0,"parameters":[0,"Yes"]},
            {"code":102,"indent":1,"parameters":[["See Intro","Skip"],1,0,2,0]},
            {"code":402,"indent":1,"parameters":[0,"See Intro"]},
            {"code":402,"indent":1,"parameters":[1,"Skip"]},
            {"code":404,"indent":1,"parameters":[]},
            {"code":402,"indent":0,"parameters":[1,"No"]},
            {"code":404,"indent":0,"parameters":[]},
            {"code":102,"indent":0,"parameters":[["Yes","hide_if(1)"],1,0,2,0]},
            {"code":402,"indent":0,"parameters":[0,"Yes"]},
            {"code":402,"indent":0,"parameters":[1,"hide_if(1)"]},
            {"code":404,"indent":0,"parameters":[]},
        ]
        doc={"events":[{"pages":[{"list":rows}]}]}
        stats=p.localize_map(doc,set(),lambda keys:({},{"new_translations":0,"cache_hits":0}),native_quality_reason)
        self.assertEqual(stats["choice_groups"],2)
        self.assertEqual(stats["choice_labels"],3)
        self.assertEqual(rows[0]["parameters"],[["Sí","No"],1,0,2,0])
        self.assertEqual(rows[1]["parameters"],[0,"Sí"])
        self.assertEqual(rows[2]["parameters"][0],["Ver introducción","Omitir"])
        self.assertEqual(rows[3]["parameters"],[0,"Ver introducción"])
        self.assertEqual(rows[8]["parameters"][0],["Yes","hide_if(1)"])
    def test_wrap_preserves_controls_and_every_word(self):
        raw=r"\C[2]\N[1] La puerta de madera está cerca del puente y debemos esperar hasta el amanecer.\C[0]"
        out,breaks,warnings=p.wrap_display(raw)
        self.assertGreater(breaks,0)
        self.assertEqual(warnings,0)
        self.assertEqual(out.replace("\n"," "),raw)
        self.assertEqual([x for x in p.CONTROL.findall(out) if x!="\n"],p.CONTROL.findall(raw))
        self.assertTrue(all(p.estimated_width(line)<=p.WRAP_PIXELS for line in out.split("\n")))
        short="Cruza el puente."
        self.assertEqual(p.wrap_display(short),(short,0,0))
    def test_malformed_map_and_duplicate_json(self):
        with self.assertRaises(ValueError):list(p.display_lines({"events":[{"pages":[{"list":[{"code":401,"indent":0,"parameters":[]}]}]}]}))
        with self.assertRaises(ValueError):p.decode(b'{"x":1,"x":2}')
if __name__=="__main__":unittest.main()
