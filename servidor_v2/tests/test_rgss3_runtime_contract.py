import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "rgss3" / "runtime" / "IATraductora_RGSS3.rb"


class RGSS3RuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PLUGIN.read_text(encoding="utf-8")

    def test_native_message_and_choice_hooks_are_present(self):
        self.assertIn("alias tx_rgss3_original_command_101 command_101", self.source)
        self.assertIn("alias tx_rgss3_original_command_102 command_102", self.source)
        self.assertIn("alias tx_rgss3_original_command_105 command_105", self.source)

    def test_first_appearance_waits_in_interpreter_fiber(self):
        self.assertIn("Fiber.yield", self.source)
        self.assertIn("MAX_WAIT_FRAMES = 1800", self.source)
        self.assertIn("translate_wait", self.source)

    def test_v95_local_bridge_only(self):
        self.assertIn('"/translate_batch"', self.source)
        self.assertIn('wide("127.0.0.1")', self.source)
        self.assertIn("X-IA-Token", self.source)
        self.assertIn("bridge.json", self.source)

    def test_f10_uses_physical_key_without_overwriting_input_mapping(self):
        self.assertIn("GetAsyncKeyState", self.source)
        self.assertIn("0x79", self.source)
        self.assertNotIn("Input.keyMapper", self.source)

    def test_only_diagnostics_window_is_added(self):
        self.assertIn("class Window_TenshixgameRGSS3Status < Window_Base", self.source)
        self.assertNotIn("Window_Message.new", self.source)
        self.assertNotIn("Window_ChoiceList.new", self.source)

    def test_name_entry_scene_is_not_hooked(self):
        self.assertNotIn("Scene_Name", self.source)
        self.assertNotIn("Window_NameInput", self.source)


if __name__ == "__main__":
    unittest.main()
