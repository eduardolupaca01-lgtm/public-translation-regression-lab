# TENSHIXGAME_VXACE_RGSS3_OWNER_V1
# Ruby 1.9.2 / RGSS3 runtime adapter. No subtitle windows are created.
require 'json'
require 'socket'
require 'timeout'
require 'digest/sha2'

module TenshixgameVXACELive
  PLUGIN_BUILD = 'VXACE-RGSS3-20261126-A'
  PLUGIN_MARKER = '# TENSHIXGAME_VXACE_RGSS3_OWNER_V1'
  PLUGIN_NAME = 'IA Traductora RGSS3'
  SIDECAR = File.join('IA Traductora', '.local', 'Rpg')
  WORKER_RELATIVE = File.join(SIDECAR, 'engine', 'IATraductora.exe')
  OWNER_RELATIVE = File.join('IA Traductora', 'owner-v1.json')
  BRIDGE_RELATIVE = File.join(SIDECAR, 'bridge.json')
  DIAGNOSTIC_RELATIVE = File.join(SIDECAR, 'diagnostics', 'vxace-live.json')
  TOKEN_PATTERN = /\\(?:N<[^>\r\n]*>|[A-Za-z]+(?:\[[^\]\r\n]*\])?|.)/
  JAPANESE_PATTERN = /[ぁ-ゖァ-ヺ一-龯]/
  LATIN_PATTERN = /[A-Za-z]/
  SPANISH_PATTERN = /[áéíóúñü¿¡]/i
  SPANISH_WORDS = %w[el la los las un una unos unas de del que y en por para con es son está están como pero muy ahora misión objetivo nuevo aceptar continuar salir volver]
  MAX_WAIT_SECONDS = 60
  HTTP_TIMEOUT_SECONDS = 8
  BATCH_SIZE = 6

  @root = nil
  @sidecar = nil
  @worker = nil
  @bridge = nil
  @worker_pid = 0
  @started = false
  @status = 'No iniciado'
  @requests = 0
  @translated = 0
  @failures = 0
  @memory = {}
  @known_translations = {}

  class << self
    attr_reader :status, :requests, :translated, :failures

    def game_root
      return @root if @root
      path = nil
      begin
        api = Win32API.new('kernel32', 'GetModuleFileNameW', 'ppl', 'i')
        buffer = "\0" * 1040
        length = api.call(0, buffer, 520)
        raise 'game executable path unavailable' if length <= 0 || length >= 520
        path = buffer[0, length * 2].force_encoding('UTF-16LE').encode('UTF-8')
      rescue StandardError
        path = File.expand_path('Game.exe')
      end
      raise 'Game.exe not found' unless path && File.file?(path)
      @root = File.dirname(File.expand_path(path))
    end

    def sidecar_path(relative)
      File.join(game_root, relative)
    end

    def ordinary_file?(path, max_bytes)
      return false if File.symlink?(path)
      return false unless File.file?(path)
      size = File.size(path)
      size > 0 && size <= max_bytes
    rescue StandardError
      false
    end

    def load_owner
      path = sidecar_path(OWNER_RELATIVE)
      raise 'VX Ace owner manifest missing' unless ordinary_file?(path, 4096)
      data = JSON.parse(File.open(path, 'rb') { |f| f.read })
      raise 'VX Ace owner schema invalid' unless data['schema'] == 'ia-traductora-owner-v1'
      raise 'VX Ace owner product invalid' unless data['product'] == 'TENSHIXGAME-SERVIDOR'
      raise 'VX Ace owner build invalid' unless data['vxace_plugin_build'] == PLUGIN_BUILD
      worker_hash = Digest::SHA256.file(@worker).hexdigest
      raise 'V95 worker hash mismatch' unless worker_hash == data['worker_sha256']
      helper_path = sidecar_path(File.join(SIDECAR, 'engine', 'vxace-helper.exe'))
      helper_hash = Digest::SHA256.file(helper_path).hexdigest
      raise 'VX Ace helper hash mismatch' unless helper_hash == data['vxace_helper_sha256']
      plugin_path = sidecar_path(File.join(SIDECAR, 'engine', 'vxace', 'TenshixgameVXACELive.rb'))
      plugin_hash = Digest::SHA256.file(plugin_path).hexdigest
      raise 'VX Ace plugin hash mismatch' unless plugin_hash == data['vxace_plugin_sha256']
      data
    end

    def process_alive?(pid)
      return false unless pid.to_i > 0
      Process.kill(0, pid.to_i)
      true
    rescue StandardError
      false
    end

    def read_bridge
      path = sidecar_path(BRIDGE_RELATIVE)
      return nil unless ordinary_file?(path, 4096)
      data = JSON.parse(File.open(path, 'rb') { |f| f.read })
      return nil unless data['schema'] == 'ia-traductora-bridge-v1'
      return nil unless data['token'].to_s =~ /\A[0-9a-fA-F]{64}\z/
      port = data['port'].to_i
      pid = data['pid'].to_i
      return nil unless port >= 1024 && port <= 65535 && pid > 0
      data
    rescue StandardError
      nil
    end

    def http_request(method, path, payload = nil)
      return nil unless @bridge
      body = payload ? JSON.generate(payload) : ''
      response = nil
      Timeout.timeout(HTTP_TIMEOUT_SECONDS) do
        socket = TCPSocket.new('127.0.0.1', @bridge['port'].to_i)
        request = method + ' ' + path + " HTTP/1.1\r\n"
        request << "Host: 127.0.0.1\r\n"
        request << "Connection: close\r\n"
        request << "X-IA-Token: " + @bridge['token'].to_s + "\r\n"
        request << "Content-Type: application/json\r\n"
        request << "Content-Length: " + body.bytesize.to_s + "\r\n\r\n"
        request << body
        socket.write(request)
        response = socket.read
        socket.close
      end
      return nil unless response
      header, response_body = response.split("\r\n\r\n", 2)
      return nil unless header && response_body
      status_line = header.split("\r\n", 2)[0].to_s
      status_code = status_line.split(' ')[1].to_i
      return nil unless status_code == 200
      JSON.parse(response_body)
    rescue StandardError
      nil
    end

    def worker_ready?(descriptor)
      @bridge = descriptor
      result = http_request('GET', '/status')
      !result.nil?
    rescue StandardError
      false
    end

    def start_worker
      return if @started
      @started = true
      @status = 'Verificando V95'
      root = game_root
      @sidecar = sidecar_path(SIDECAR)
      @worker = sidecar_path(WORKER_RELATIVE)
      owner = load_owner
      raise 'V95 worker missing' unless ordinary_file?(@worker, 450 * 1024 * 1024)
      actual = Digest::SHA256.file(@worker).hexdigest
      raise 'V95 worker hash mismatch' unless actual == owner['worker_sha256']
      descriptor = read_bridge
      if descriptor && worker_ready?(descriptor)
        @worker_pid = descriptor['pid'].to_i
        @status = 'V95 activo'
        return
      end
      if descriptor && process_alive?(descriptor['pid'])
        raise 'Existing V95 process does not match the game bridge'
      end
      diagnostic = sidecar_path(DIAGNOSTIC_RELATIVE)
      diagnostic_dir = File.dirname(diagnostic)
      Dir.mkdir(diagnostic_dir) unless File.directory?(diagnostic_dir)
      @worker_pid = Process.spawn(
        @worker,
        '--game-root', root,
        '--parent-pid', Process.pid.to_s,
        '--diagnostic-file', diagnostic,
        :chdir => root,
        :out => 'NUL',
        :err => 'NUL'
      )
      Process.detach(@worker_pid)
      @status = 'V95 iniciando'
    rescue StandardError
      @status = 'V95 no disponible'
      @worker_pid = 0
    end

    def ensure_bridge
      return true if @bridge && worker_ready?(@bridge)
      start_worker unless @started
      deadline = Time.now.to_i + MAX_WAIT_SECONDS
      while Time.now.to_i <= deadline
        descriptor = read_bridge
        if descriptor && worker_ready?(descriptor)
          @bridge = descriptor
          @worker_pid = descriptor['pid'].to_i
          @status = 'V95 activo'
          return true
        end
        sleep 0.25
      end
      @status = 'V95 sin respuesta'
      false
    end

    def source_language(text)
      text.to_s =~ JAPANESE_PATTERN ? 'ja' : 'en'
    end

    def spanish_text?(text)
      value = text.to_s
      return true if value =~ SPANISH_PATTERN
      words = value.downcase.scan(/[a-záéíóúñü]+/)
      return false if words.empty?
      matches = words.count { |word| SPANISH_WORDS.include?(word) }
      matches >= 2 || (matches >= 1 && words.length <= 4 && value !~ JAPANESE_PATTERN)
    end

    def translatable_segment?(text)
      value = text.to_s.strip
      return false if value.empty? || value.length > 1800
      return false unless value =~ /[A-Za-zぁ-ゖァ-ヺ一-龯]/
      return false if spanish_text?(value)
      true
    end

    def translate_segments(segments)
      results = segments.dup
      pending = {}
      segments.each_with_index do |text, index|
        value = text.to_s
        if @memory.key?(value)
          results[index] = @memory[value]
        elsif @known_translations.key?(value) || !translatable_segment?(value)
          results[index] = value
        else
          lang = source_language(value)
          pending[lang] ||= []
          pending[lang] << [index, value]
        end
      end
      return results if pending.empty?
      return results unless ensure_bridge
      pending.each do |lang, entries|
        entries.each_slice(BATCH_SIZE) do |slice|
          texts = slice.map { |entry| entry[1] }
          @requests += texts.length
          response = http_request('POST', '/translate_batch', {
            'source' => lang,
            'target' => 'es',
            'texts' => texts
          })
          translations = response && response['results']
          if !translations.is_a?(Array) || translations.length != texts.length
            @failures += texts.length
            next
          end
          slice.each_with_index do |entry, offset|
            index = entry[0]
            original = entry[1]
            translated = translations[offset]
            if translated.is_a?(String) && !translated.strip.empty? && translated != original
              value = translated.strip
              results[index] = value
              @memory[original] = value
              @known_translations[value] = true
              @translated += 1
            else
              results[index] = original
              @failures += 1
            end
          end
        end
      end
      results
    end

    def split_controls(text)
      value = text.to_s
      segments = []
      cursor = 0
      value.to_enum(:scan, TOKEN_PATTERN).each do
        match = Regexp.last_match
        first = match.begin(0)
        last = match.end(0)
        segments << [:text, value[cursor...first]] if first > cursor
        segments << [:token, match[0]]
        cursor = last
      end
      segments << [:text, value[cursor..-1]] if cursor < value.length
      segments
    end

    def translate_with_controls_batch(strings)
      parsed = strings.map { |value| split_controls(value) }
      text_refs = []
      parsed.each_with_index do |segments, row|
        segments.each_with_index do |segment, col|
          if segment[0] == :text && translatable_segment?(segment[1])
            text_refs << [row, col, segment[1]]
          end
        end
      end
      translations = translate_segments(text_refs.map { |item| item[2] })
      text_refs.each_with_index do |item, index|
        parsed[item[0]][item[1]][1] = translations[index]
      end
      parsed.map do |segments|
        segments.map { |segment| segment[1] }.join
      end
    rescue StandardError
      strings
    end

    def translate(text)
      translate_with_controls_batch([text]).first
    end

    def name_input_active?
      return false unless defined?(SceneManager) && defined?(Scene_Name)
      SceneManager.scene_is?(Scene_Name)
    rescue StandardError
      false
    end

    def toggle_diagnostics(window)
      return unless window
      window.visible = !window.visible
      window.refresh if window.visible
    end

    def start
      start_worker
    end
  end
end

# Hook the native RGSS3 message queue. The translated text is inserted before
# Window_Message draws it; no second subtitle window or bitmap overlay is used.
class Game_Message
  alias_method :ia_vxace_original_add, :add
  def add(text)
    value = TenshixgameVXACELive.translate(text)
    ia_vxace_original_add(value)
  end

  if method_defined?(:choices=)
    alias_method :ia_vxace_original_choices_set, :choices=
    def choices=(value)
      translated = value.is_a?(Array) ? TenshixgameVXACELive.translate_with_controls_batch(value) : value
      ia_vxace_original_choices_set(translated)
    end
  end
end

# Catch labels rendered by native menu, item, skill and status windows. The
# name-entry scene is intentionally excluded so player input is never changed.
class Window_Base
  alias_method :ia_vxace_original_draw_text, :draw_text
  def draw_text(*args)
    unless TenshixgameVXACELive.name_input_active?
      index = nil
      index = 0 if args[0].is_a?(String)
      index = 1 if index.nil? && args[1].is_a?(String)
      index = 4 if index.nil? && args[4].is_a?(String)
      if index
        copy = args.dup
        copy[index] = TenshixgameVXACELive.translate(copy[index])
        return ia_vxace_original_draw_text(*copy)
      end
    end
    ia_vxace_original_draw_text(*args)
  end
end

class Window_TenshixgameVXACEDiagnostics < Window_Base
  def initialize
    super(8, 8, 380, 128)
    self.opacity = 220
    self.visible = false
    self.z = 9999
    refresh
  end

  def refresh
    contents.clear
    contents.draw_text(0, 0, contents.width, 24, 'TENSHIXGAME RPG - VX Ace')
    contents.draw_text(0, 24, contents.width, 24, 'Estado: ' + TenshixgameVXACELive.status.to_s)
    contents.draw_text(0, 48, contents.width, 24, 'Solicitudes: ' + TenshixgameVXACELive.requests.to_s)
    contents.draw_text(0, 72, contents.width, 24, 'Traducidas: ' + TenshixgameVXACELive.translated.to_s)
    contents.draw_text(0, 96, contents.width, 24, 'Fallidas: ' + TenshixgameVXACELive.failures.to_s)
  end
end

class Scene_Map
  alias_method :ia_vxace_original_start, :start
  def start
    ia_vxace_original_start
    @ia_vxace_diagnostics = Window_TenshixgameVXACEDiagnostics.new
  end

  alias_method :ia_vxace_original_update, :update
  def update
    ia_vxace_original_update
    if Input.trigger?(:F10)
      TenshixgameVXACELive.toggle_diagnostics(@ia_vxace_diagnostics)
    end
  end

  alias_method :ia_vxace_original_terminate, :terminate
  def terminate
    if @ia_vxace_diagnostics && !@ia_vxace_diagnostics.disposed?
      @ia_vxace_diagnostics.dispose
    end
    ia_vxace_original_terminate
  end
end

TenshixgameVXACELive.start
