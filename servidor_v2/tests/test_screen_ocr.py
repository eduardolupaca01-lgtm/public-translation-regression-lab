import importlib.util, tempfile, unittest
from pathlib import Path
worker_dir=Path(__file__).resolve().parents[1]/"worker"
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,worker_dir/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
screen=load("screen_ocr_test","screen_ocr.py")
ia=load("ia_screen_test","IATraductora.py")
class ScreenTests(unittest.TestCase):
    def test_preserves_long_original(self):
        value=("Texto de prueba para no perder contenido. "*200)+"FINAL"
        parts=screen.split_text(value)
        self.assertEqual("".join(parts),value)
        self.assertTrue(all(len(p)<=1800 for p in parts))
    def test_dialogue_and_menu(self):
        calls=[]
        def translate(lang,text):
            calls.append((lang,text));return "ES:"+text
        self.assertEqual(screen.translate_lines(("Good","morning"),"en","dialogue",translate),("Good\nmorning","ES:Good morning",0))
        self.assertEqual(screen.translate_lines(("Item","Save"),"en","menu",translate),("Item\nSave","ES:Item\nES:Save",0))
        self.assertEqual(calls,[("en","Good morning"),("en","Item"),("en","Save")])
    def test_failed_segment_retained(self):
        def translate(lang,text):
            if text=="Save":raise RuntimeError("failure")
            return "Objetos"
        self.assertEqual(screen.translate_lines(("Item","Save"),"en","menu",translate),("Item\nSave","Objetos\nSave",1))
    def test_region_tracks_resize(self):
        region=screen.normalized_box((400,220),(100,100),500,300)
        self.assertEqual(screen.pixel_box((10,20,1010,620),region),(210,220,810,460))
        self.assertFalse(screen.overlaps((0,0,10,10),(10,0,20,10)))
        self.assertTrue(screen.overlaps((0,0,10,10),(9,0,20,10)))
    def test_screen_service_cache_persists_without_game(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/"IA Traductora"/".local"/"Rpg").mkdir(parents=True)
            engine=root/"versions"/"engine";engine.mkdir(parents=True)
            class Neural:
                def translate(self,lang,text):return "Buenos días"
            service=ia.Service(root,engine,neural=Neural(),screen_profile=True)
            self.assertEqual(service.translate("en","Good morning"),"Buenos días")
            service.close()
            class NoInference:
                def translate(self,*args):raise AssertionError("must use cache")
            again=ia.Service(root,engine,neural=NoInference(),screen_profile=True)
            try:self.assertEqual(again.translate("en","Good morning"),"Buenos días")
            finally:again.close()
            with self.assertRaises(ValueError):ia.Service(root,engine,neural=Neural())
