# Frozen runtime contract test. The RGSS3 plugin is loaded against minimal
# engine stubs so its native event hooks and control-code handling are exercised
# without launching a real game or a worker process.
require "minitest/autorun"
require "tmpdir"

class Win32API
  class << self
    attr_accessor :key_down
  end
  def initialize(_dll, name, _imports, _returns)
    @name = name
  end
  def call(*_args)
    return self.class.key_down ? 0x8000 : 0 if @name == "GetAsyncKeyState"
    return 33 if @name == "ShellExecuteW"
    1
  end
end
Win32API.key_down = false

module Graphics
  def self.width; 544; end
  def self.frame_count; 0; end
end

class TestContents
  def width; 300; end
  def clear; true; end
end

class Window_Base
  attr_accessor :opacity
  def initialize(*_args); @contents = TestContents.new; end
  def contents; @contents; end
  def draw_text(*_args); true; end
  def dispose; @disposed = true; end
end

class Game_Interpreter
  attr_accessor :list, :index, :params, :captured
  def command_101
    @captured = @list[@index + 1].parameters[0]
    true
  end
  def command_102
    @captured = @params[0].dup
    true
  end
  def command_105
    @captured = @list[@index + 1].parameters[0]
    true
  end
end

class Scene_Map
  def update; true; end
  def terminate; true; end
end

EventCommand = Struct.new(:code, :parameters)

Dir.mktmpdir("rgss3-runtime-test") do |directory|
  Dir.chdir(directory) do
    load File.expand_path("../rgss3/runtime/IATraductora_RGSS3.rb", __dir__)
  end
end

class RGSS3RuntimeBehaviorTest < Minitest::Test
  def translate_with
    TenshixgameRGSS3.define_singleton_method(:translate_wait) do |texts|
      yield(texts)
    end
  end

  def test_detect_source_language
    assert_equal "ja", TenshixgameRGSS3.detect_source(["こんにちは"])
    assert_equal "en", TenshixgameRGSS3.detect_source(["Hello there"])
  end

  def test_control_codes_are_preserved_exactly
    source = "Hola \\C[3]mundo \\V[2]"
    protected, markers = TenshixgameRGSS3.protect_codes(source)
    refute_includes protected, "\\C[3]"
    assert_equal "Hello \\C[3]world \\V[2]",
      TenshixgameRGSS3.restore_codes("Hello " + protected.split(" ").first.to_s + "world", markers) rescue nil
    restored = TenshixgameRGSS3.restore_codes(protected, markers)
    assert_equal source, restored
  end

  def test_missing_or_duplicated_control_markers_are_rejected
    _protected, markers = TenshixgameRGSS3.protect_codes("Hola \\C[3]")
    marker = markers.first[0]
    assert_raises(RuntimeError) do
      TenshixgameRGSS3.restore_codes(marker + marker, markers)
    end
  end

  def test_message_hook_translates_before_original_command_and_restores_event_data
    commands = [
      EventCommand.new(101, []),
      EventCommand.new(401, ["こんにちは"]),
      EventCommand.new(401, ["元気ですか？"]),
      EventCommand.new(0, []),
    ]
    interpreter = Game_Interpreter.new
    interpreter.list = commands
    interpreter.index = 0
    translate_with { |texts| ["Hola.", "¿Cómo estás?"] }
    interpreter.command_101
    assert_equal "Hola.", interpreter.captured
    assert_equal ["こんにちは", "元気ですか？"],
      interpreter.list[1..2].map { |item| item.parameters[0] }
  end

  def test_choice_hook_translates_native_choices_and_restores_originals
    interpreter = Game_Interpreter.new
    interpreter.params = [["Sí", "No"], 0]
    translate_with { |texts| ["Yes", "No"] }
    interpreter.command_102
    assert_equal ["Yes", "No"], interpreter.captured
    assert_equal ["Sí", "No"], interpreter.params[0]
  end

  def test_scroll_text_hook_translates_before_original_and_restores_event_data
    commands = [
      EventCommand.new(105, []),
      EventCommand.new(405, ["Texto desplazable"]),
      EventCommand.new(405, ["Segunda línea"]),
      EventCommand.new(0, []),
    ]
    interpreter = Game_Interpreter.new
    interpreter.list = commands
    interpreter.index = 0
    translate_with { |texts| ["Scrolling text", "Second line"] }
    interpreter.command_105
    assert_equal "Scrolling text", interpreter.captured
    assert_equal ["Texto desplazable", "Segunda línea"],
      interpreter.list[1..2].map { |item| item.parameters[0] }
  end

  def test_f10_is_edge_triggered_without_changing_input_mapping
    Win32API.key_down = true
    assert_equal true, TenshixgameRGSS3.f10_pressed?
    assert_equal false, TenshixgameRGSS3.f10_pressed?
    Win32API.key_down = false
    assert_equal false, TenshixgameRGSS3.f10_pressed?
    Win32API.key_down = true
    assert_equal true, TenshixgameRGSS3.f10_pressed?
  ensure
    Win32API.key_down = false
  end

  def test_diagnostic_panel_is_only_a_status_window
    window = Window_TenshixgameRGSS3Status.new
    assert_equal 230, window.opacity
    assert_includes TenshixgameRGSS3.status_lines.join(" "), "TENSHIXGAME RPG - VX ACE"
  end
end
