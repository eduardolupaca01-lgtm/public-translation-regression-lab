# encoding: UTF-8
# TENSHIXGAME_RGSS3_RUNTIME_V1
# RPG Maker VX Ace / RGSS3. Native message and choice replacement only.
# No subtitle window is created. F10 opens diagnostics only.

require 'json'

module TenshixgameRGSS3
  VERSION = "RGSS3-V1"
  MAX_WAIT_FRAMES = 1800
  BATCH_SIZE = 6
  CONTROL_PATTERN = /\\(?:[A-Za-z]+(?:\[[^\]]*\])?|[.!|^><{}$])/

  @mutex = Mutex.new
  @jobs = {}
  @next_job = 1
  @bridge = nil
  @worker_started = false
  @status = "INICIANDO"
  @translated = 0
  @failed = 0
  @cache = 0
  @f10_last_down = false

  def self.game_root
    File.expand_path(".")
  end

  def self.sidecar_root
    File.join(game_root, "IA Traductora", ".local", "Rpg")
  end

  def self.bridge_path
    File.join(sidecar_root, "bridge.json")
  end

  def self.worker_path
    File.join(sidecar_root, "engine", "IATraductora.exe")
  end

  def self.wide(value)
    value.to_s.encode("UTF-16LE") + "\0\0"
  end

  def self.win_api(dll, name, imports, returns)
    Win32API.new(dll, name, imports, returns)
  end

  def self.start_worker
    return if @worker_started
    @worker_started = true
    unless File.file?(worker_path)
      @status = "WORKER NO INSTALADO"
      return
    end
    begin
      get_pid = win_api("kernel32", "GetCurrentProcessId", "", "L")
      shell = win_api("shell32", "ShellExecuteW", "PPPPPL", "L")
      pid = get_pid.call
      args = "--game-root #{wide(game_root)} --parent-pid #{pid}"
      result = shell.call(nil, wide("open"), wide(worker_path), wide(args), wide(game_root), 0)
      @status = result.to_i > 32 ? "CONECTANDO" : "ERROR AL INICIAR"
    rescue
      @status = "ERROR AL INICIAR"
    end
    Thread.new { wait_for_bridge }
  end

  def self.wait_for_bridge
    120.times do
      begin
        if File.file?(bridge_path)
          item = JSON.parse(File.read(bridge_path))
          if item.is_a?(Hash) && item["port"].to_i > 0 &&
             item["port"].to_i <= 65535 && item["token"].to_s.length >= 32
            @mutex.synchronize { @bridge = item }
            @status = "V95 CONECTADO"
            return true
          end
        end
      rescue
      end
      sleep(0.25)
    end
    @status = "V95 SIN RESPUESTA"
    false
  end

  def self.bridge
    @mutex.synchronize { @bridge }
  end

  def self.http_request(path, payload = nil)
    info = bridge
    raise "IA_BRIDGE_NOT_READY" unless info
    open_api = win_api("winhttp", "WinHttpOpen", "PLPPL", "L")
    connect_api = win_api("winhttp", "WinHttpConnect", "PLPL", "L")
    request_api = win_api("winhttp", "WinHttpOpenRequest", "PPPPPPP", "L")
    send_api = win_api("winhttp", "WinHttpSendRequest", "PLPLLLL", "L")
    receive_api = win_api("winhttp", "WinHttpReceiveResponse", "PP", "L")
    available_api = win_api("winhttp", "WinHttpQueryDataAvailable", "PP", "L")
    read_api = win_api("winhttp", "WinHttpReadData", "PLPP", "L")
    close_api = win_api("winhttp", "WinHttpCloseHandle", "L", "L")
    timeout_api = win_api("winhttp", "WinHttpSetTimeouts", "LLLLL", "L")

    session = open_api.call(wide("TENSHIXGAME-RGSS3"), 1, nil, nil, 0)
    raise "IA_WINHTTP_OPEN" if session.to_i == 0
    connection = 0
    request = 0
    begin
      timeout_api.call(session, 3000, 3000, 12000, 20000)
      connection = connect_api.call(session, wide("127.0.0.1"), info["port"].to_i, 0)
      raise "IA_WINHTTP_CONNECT" if connection.to_i == 0
      method = payload.nil? ? "GET" : "POST"
      request = request_api.call(connection, wide(method), wide(path), nil, nil, nil, 0)
      raise "IA_WINHTTP_REQUEST" if request.to_i == 0
      if payload
        body = JSON.generate(payload)
        headers = wide("Content-Type: application/json\r\nX-IA-Token: #{info["token"]}\r\n")
        sent = send_api.call(request, headers, -1, body, body.bytesize, body.bytesize, 0)
      else
        headers = wide("X-IA-Token: #{info["token"]}\r\n")
        sent = send_api.call(request, headers, -1, nil, 0, 0, 0)
      end
      raise "IA_WINHTTP_SEND" if sent.to_i == 0
      raise "IA_WINHTTP_RECEIVE" if receive_api.call(request, nil).to_i == 0

      response = ""
      loop do
        available = [0].pack("L")
        raise "IA_WINHTTP_AVAILABLE" if available_api.call(request, available).to_i == 0
        count = available.unpack("L")[0]
        break if count == 0
        buffer = "\0" * count
        read_count = [0].pack("L")
        raise "IA_WINHTTP_READ" if read_api.call(request, buffer, count, read_count).to_i == 0
        read = read_count.unpack("L")[0]
        break if read == 0
        response << buffer[0, read]
        raise "IA_WINHTTP_RESPONSE_TOO_LARGE" if response.bytesize > 65536
      end
      JSON.parse(response)
    ensure
      close_api.call(request) if request.to_i != 0
      close_api.call(connection) if connection.to_i != 0
      close_api.call(session) if session.to_i != 0
    end
  end

  def self.detect_source(texts)
    joined = texts.join("\n")
    joined =~ /[\u3040-\u30ff\u3400-\u9fff]/ ? "ja" : "en"
  end

  def self.protect_codes(text)
    markers = []
    protected = text.to_s.gsub(CONTROL_PATTERN) do |code|
      marker = "__TXRGSS3_CODE_#{markers.length}__"
      markers << [marker, code]
      marker
    end
    [protected, markers]
  end

  def self.restore_codes(text, markers)
    result = text.to_s.dup
    markers.each do |marker, original|
      count = result.scan(Regexp.new(Regexp.escape(marker))).length
      raise "IA_MARKER_MISSING_OR_DUPLICATED" unless count == 1
      result = result.sub(marker, original)
    end
    raise "IA_MARKER_REMAINS" if result.include?("__TXRGSS3_CODE_")
    result
  end

  def self.translate_now(texts)
    output = []
    texts.each_slice(BATCH_SIZE) do |slice|
      protected = slice.map { |text| protect_codes(text) }
      request = {
        "source" => detect_source(slice),
        "target" => "es",
        "texts" => protected.map { |item| item[0] }
      }
      response = http_request("/translate_batch", request)
      results = response["results"]
      raise "IA_BATCH_SHAPE" unless results.is_a?(Array) && results.length == slice.length
      results.each_with_index do |item, index|
        if item.is_a?(Hash) && item["translated"].is_a?(String) &&
           !item["translated"].strip.empty?
          begin
            output << restore_codes(item["translated"], protected[index][1])
            @translated += 1
          rescue
            output << slice[index]
            @failed += 1
          end
        else
          output << slice[index]
          @failed += 1
        end
      end
    end
    output
  end

  def self.request(texts)
    return nil unless texts.is_a?(Array) && !texts.empty?
    start_worker unless @worker_started
    id = nil
    @mutex.synchronize do
      id = @next_job
      @next_job += 1
      @jobs[id] = { :done => false, :result => nil, :error => nil }
    end
    Thread.new do
      begin
        wait_for_bridge unless bridge
        raise "IA_BRIDGE_NOT_READY" unless bridge
        result = translate_now(texts)
        @mutex.synchronize { @jobs[id][:result] = result }
      rescue
        @failed += texts.length
        @mutex.synchronize { @jobs[id][:error] = "IA_TRANSLATION_FAILED" }
      ensure
        @mutex.synchronize { @jobs[id][:done] = true }
      end
    end
    id
  end

  def self.await(id)
    return nil unless id
    frames = 0
    loop do
      job = @mutex.synchronize { @jobs[id] }
      break unless job && !job[:done]
      break if frames >= MAX_WAIT_FRAMES
      begin
        Fiber.yield
      rescue FiberError
        sleep(0.01)
      end
      frames += 1
    end
    job = @mutex.synchronize { @jobs.delete(id) }
    return nil unless job && job[:done] && !job[:error]
    job[:result]
  end

  def self.translate_wait(texts)
    id = request(texts)
    await(id)
  end

  def self.f10_pressed?
    api = win_api("user32", "GetAsyncKeyState", "L", "L")
    down = (api.call(0x79).to_i & 0x8000) != 0
    pressed = down && !@f10_last_down
    @f10_last_down = down
    pressed
  rescue
    false
  end

  def self.status_lines
    [
      "TENSHIXGAME RPG - VX ACE",
      "V95: #{@status}",
      "TRADUCCIONES: #{@translated}",
      "FALLOS: #{@failed}",
      "F10: CERRAR"
    ]
  end
end

class Game_Interpreter
  alias tx_rgss3_original_command_101 command_101
  def command_101
    originals = []
    if @list && @index && TenshixgameRGSS3
      rows = []
      cursor = @index + 1
      while @list[cursor] && @list[cursor].code == 401
        rows << [cursor, @list[cursor].parameters[0]]
        cursor += 1
      end
      unless rows.empty?
        translated = TenshixgameRGSS3.translate_wait(rows.map { |row| row[1] })
        if translated && translated.length == rows.length
          rows.each_with_index do |row, i|
            originals << [row[0], row[1]]
            @list[row[0]].parameters[0] = translated[i]
          end
        end
      end
    end
    tx_rgss3_original_command_101
  ensure
    originals.each do |index, text|
      @list[index].parameters[0] = text if @list && @list[index]
    end
  end

  alias tx_rgss3_original_command_102 command_102
  def command_102
    original_choices = @params && @params[0].is_a?(Array) ? @params[0].dup : nil
    if original_choices && !original_choices.empty?
      translated = TenshixgameRGSS3.translate_wait(original_choices)
      @params[0] = translated if translated && translated.length == original_choices.length
    end
    tx_rgss3_original_command_102
  ensure
    @params[0] = original_choices if original_choices && @params
  end

  alias tx_rgss3_original_command_105 command_105
  def command_105
    originals = []
    if @list && @index
      rows = []
      cursor = @index + 1
      while @list[cursor] && @list[cursor].code == 405
        rows << [cursor, @list[cursor].parameters[0]]
        cursor += 1
      end
      unless rows.empty?
        translated = TenshixgameRGSS3.translate_wait(rows.map { |row| row[1] })
        if translated && translated.length == rows.length
          rows.each_with_index do |row, i|
            originals << [row[0], row[1]]
            @list[row[0]].parameters[0] = translated[i]
          end
        end
      end
    end
    tx_rgss3_original_command_105
  ensure
    originals.each do |index, text|
      @list[index].parameters[0] = text if @list && @list[index]
    end
  end
end

class Window_TenshixgameRGSS3Status < Window_Base
  def initialize
    super(Graphics.width - 340, 12, 328, 144)
    self.opacity = 230
    refresh
  end

  def refresh
    contents.clear
    TenshixgameRGSS3.status_lines.each_with_index do |line, index|
      draw_text(0, index * 24, contents.width, 24, line, 0)
    end
  end
end

class Scene_Map
  alias tx_rgss3_original_update update
  def update
    tx_rgss3_original_update
    if TenshixgameRGSS3.f10_pressed?
      if @tx_rgss3_status_window
        @tx_rgss3_status_window.dispose
        @tx_rgss3_status_window = nil
      else
        @tx_rgss3_status_window = Window_TenshixgameRGSS3Status.new
      end
    end
    if @tx_rgss3_status_window && Graphics.frame_count % 30 == 0
      @tx_rgss3_status_window.refresh
    end
  end

  alias tx_rgss3_original_terminate terminate
  def terminate
    if @tx_rgss3_status_window
      @tx_rgss3_status_window.dispose
      @tx_rgss3_status_window = nil
    end
    tx_rgss3_original_terminate
  end
end

TenshixgameRGSS3.start_worker
