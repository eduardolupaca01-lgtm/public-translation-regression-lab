# encoding: UTF-8
# IA_TRADUCTORA_VXACE_RGSS3_OWNER_V1
# Servidor / Ruby 1.9.2 core-only adapter. No socket, JSON, gems or overlay.
# The verified native helper launches the same game-local OPUS worker.
module IATraductoraVXACE
  PLUGIN_BUILD = 'VXACE-RGSS3-20261126-C'
  SIDECAR = File.join('IA Traductora', '.local', 'Rpg')
  SESSION = 'IA-VXACE-SESSION-1'
  REQUEST = 'IA-VXACE-REQUEST-1'
  RESPONSE = 'IA-VXACE-RESPONSE-1'
  MAX_BYTES = 96 * 1024
  MAX_TEXT = 1800
  MAX_WAIT = 45.0
  MAX_CACHE = 8192
  # Preserve control codes, escaped backslashes, line breaks and format fields.
  CONTROLS = /(\\(?:[A-Za-z]+(?:\[[^\]\r\n]*\]|<[^>\r\n]*>)?|.)|\r\n|\r|\n|%[0-9]+|%[sd]|\{[A-Za-z_][A-Za-z0-9_]*\})/
  JAPANESE = /[ぁ-ゖァ-ヺ一-龯]/
  @serial = 0
  @memory = {}
  @started = false
  @status = 'No iniciado'
  @requests = 0
  @translated = 0
  @failures = 0
  @f10_down = false

  class << self
    attr_reader :status, :requests, :translated, :failures

    def wide(value)
      (value.encode('UTF-16LE') + "\0\0".force_encoding('UTF-16LE')).force_encoding('ASCII-8BIT')
    end

    def root
      return @root if @root
      path = nil
      if defined?(Win32API)
        api = Win32API.new('kernel32', 'GetModuleFileNameW', 'lpl', 'l')
        buffer = ("\0" * 65536).force_encoding('ASCII-8BIT')
        count = api.call(0, buffer, 32768)
        if count > 0 && count < 32768
          path = buffer[0, count * 2].force_encoding('UTF-16LE').encode('UTF-8')
        end
      end
      # RGSS3 normally starts with the game directory as cwd; the fallback
      # also permits the explicitly synthetic desktop-Ruby acceptance harness.
      candidate = path && File.basename(path).downcase == 'game.exe' ? File.dirname(path) : Dir.pwd
      candidate = File.realpath(candidate)
      raise 'IA_VXACE_GAME_ROOT' unless File.file?(File.join(candidate, 'Game.exe'))
      @root = candidate
    end

    def local(*parts)
      File.join(root, SIDECAR, *parts)
    end

    def safe_file?(path, limit)
      !File.symlink?(path) && File.file?(path) && File.size(path) > 0 && File.size(path) <= limit
    rescue StandardError
      false
    end

    def bounded_read(path, limit)
      return nil unless safe_file?(path, limit)
      value = File.open(path, 'rb') { |f| f.read(limit + 1) }
      value && value.bytesize <= limit ? value : nil
    rescue StandardError
      nil
    end

    def inside_directory?(path)
      return false if File.symlink?(path) || !File.directory?(path)
      prefix = File.realpath(local).tr('\\', '/').downcase + '/'
      File.realpath(path).tr('\\', '/').downcase.index(prefix) == 0
    rescue StandardError
      false
    end

    def start
      return if @started
      @started = true
      @status = 'Iniciando OPUS'
      helper = local('engine', 'vxace-helper.exe')
      raise 'IA_VXACE_HELPER' unless safe_file?(helper, 128 * 1024 * 1024)
      args = 'launch-worker --parent-pid ' + Process.pid.to_s
      if defined?(Win32API)
        shell = Win32API.new('shell32', 'ShellExecuteW', 'lppppl', 'l')
        result = shell.call(0, wide('open'), wide(helper), wide(args), wide(root), 0)
        raise 'IA_VXACE_LAUNCH' if result <= 32
      else
        # Desktop Ruby fixture: no shell and no externally provided command.
        pid = Process.spawn(helper, 'launch-worker', '--parent-pid', Process.pid.to_s,
                            :chdir => root, :out => File::NULL, :err => File::NULL)
        Process.detach(pid)
      end
    rescue StandardError
      @status = 'OPUS no disponible'
    end

    def session
      raw = bounded_read(local('vxace-session.txt'), 512)
      return nil unless raw
      lines = raw.split("\n")
      return nil unless lines.length == 4 && lines[0] == SESSION &&
        lines[1] =~ /\A[0-9a-f]{64}\z/ && lines[2] =~ /\A[1-9][0-9]*\z/ &&
        lines[3] == Process.pid.to_s
      directory = local('vxace-ipc', lines[1])
      return nil unless inside_directory?(directory)
      @status = 'OPUS activo'
      [lines[1], directory]
    rescue StandardError
      nil
    end

    def source(text)
      return 'ja' if text =~ JAPANESE
      return 'en' if text =~ /[A-Za-z]/
      nil
    end

    def parts(text)
      return [text] unless text.is_a?(String)
      utf8 = text.dup.force_encoding('UTF-8')
      return [text] unless utf8.valid_encoding?
      utf8.split(CONTROLS, -1)
    rescue StandardError
      [text]
    end

    def remember(key, value)
      @memory[key] = value
      @memory.shift while @memory.size > MAX_CACHE
    end

    def plan(strings)
      parsed = strings.map { |s| parts(s) }
      refs = {}
      parsed.each_with_index do |row, i|
        row.each_with_index do |piece, j|
          next if j.odd? || !piece.is_a?(String) || !piece.valid_encoding?
          next if piece =~ /[\x00-\x1f\\]/
          core = piece.strip
          lang = source(core)
          next if !lang || core.empty? || core.length > MAX_TEXT
          # Preserve original whitespace and controls; the model sees prose.
          head = piece[/\A\s*/] || ''
          tail = piece[/\s*\z/] || ''
          key = [lang, core]
          if @memory.key?(key)
            row[j] = head + @memory[key] + tail
          else
            (refs[key] ||= []) << [i, j, head, tail]
          end
        end
      end
      queue = []
      ['ja','en'].each do |lang|
        refs.keys.select { |key| key[0] == lang }.each_slice(6) { |keys| queue << keys }
      end
      { :parsed => parsed, :refs => refs, :queue => queue, :active => nil,
        :deadline => Time.now.to_f + MAX_WAIT, :next_poll => 0.0 }
    end

    def valid_translation?(value, key)
      value && value.valid_encoding? && !value.strip.empty? && value != key[1] &&
        !(value =~ /[\\\x00-\x1f]/) &&
        !(key[0] == 'ja' && value =~ JAPANESE)
    end

    def send_batch(p, keys, descriptor)
      token, directory = descriptor
      @serial += 1
      ident = sprintf('%016x', @serial)
      base = File.join(directory, ident)
      data = ([REQUEST, token, keys[0][0]] + keys.map { |key| key[1].unpack('H*')[0] }).join("\n") + "\n"
      return false if data.bytesize > MAX_BYTES || File.exist?(base + '.req') || File.exist?(base + '.res')
      temporary = base + '.tmp'
      created = false
      begin
        File.open(temporary, File::WRONLY | File::CREAT | File::EXCL | File::BINARY) do |f|
          created = true
          f.write(data)
        end
        File.rename(temporary, base + '.req')
        p[:active] = [token, ident, base, keys]
        @requests += keys.length
        true
      ensure
        File.delete(temporary) if created && File.file?(temporary) && !File.symlink?(temporary)
      end
    rescue StandardError
      false
    end

    def receive_batch(p)
      token, ident, base, keys = p[:active]
      raw = bounded_read(base + '.res', MAX_BYTES)
      return false unless raw
      lines = raw.split("\n")
      File.delete(base + '.res') unless File.symlink?(base + '.res')
      valid = lines.length == keys.length + 3 && lines[0] == RESPONSE && lines[1] == token && lines[2] == ident
      keys.each_with_index do |key, index|
        hex = valid ? lines[index + 3] : nil
        value = nil
        if hex && hex =~ /\A(?:[0-9a-f]{2})+\z/
          value = [hex].pack('H*').force_encoding('UTF-8')
        end
        if valid_translation?(value, key)
          remember(key, value)
          p[:refs][key].each { |i,j,head,tail| p[:parsed][i][j] = head + value + tail }
          @translated += 1
        else
          @failures += 1
        end
      end
      p[:active] = nil
      true
    rescue StandardError
      false
    end

    def advance(p)
      return true if p[:queue].empty? && !p[:active]
      if Time.now.to_f >= p[:deadline]
        @failures += p[:queue].inject(0) { |n,keys| n + keys.length }
        @failures += p[:active][3].length if p[:active]
        @status = 'Espera agotada; original conservado'
        return true
      end
      return false if Time.now.to_f < p[:next_poll]
      p[:next_poll] = Time.now.to_f + 0.04
      if p[:active]
        return false unless receive_batch(p)
      end
      return true if p[:queue].empty?
      start
      descriptor = session
      return false unless descriptor
      keys = p[:queue].first
      p[:queue].shift if send_batch(p, keys, descriptor)
      false
    end

    def result(p)
      p[:parsed].map { |row| row.join }
    end

    # Only the original rendering call sees translated strings. The original
    # event arrays and choice callbacks are restored, not persisted into saves.
    def around_native(array)
      return yield unless array.is_a?(Array) && !array.empty?
      original = array.dup
      p = plan(original)
      Fiber.yield until advance(p)
      return yield unless array == original
      translated = result(p)
      array.replace(translated)
      begin
        yield
      ensure
        array.replace(original) if array == translated
      end
    end

    def f10?
      if defined?(Win32API)
        @foreground_api ||= Win32API.new('user32','GetForegroundWindow','','l')
        @window_pid_api ||= Win32API.new('user32','GetWindowThreadProcessId','lp','l')
        @key_api ||= Win32API.new('user32','GetAsyncKeyState','i','i')
        pid = [0].pack('L')
        @window_pid_api.call(@foreground_api.call, pid)
        down = pid.unpack('L')[0] == Process.pid && (@key_api.call(0x79) & 0x8000) != 0
        edge = down && !@f10_down
        @f10_down = down
        return edge
      end
      false
    rescue StandardError
      false
    end
  end
end

# Standard VX Ace pushes choices into an existing array, without calling a
# setter. Intercept at the native render boundary, not the setter or pixels.
# These methods execute inside the message window's existing fiber.
if defined?(Window_Message) && Window_Message.method_defined?(:process_all_text)
  class Window_Message
    alias_method :ia_vxace_original_process_all_text, :process_all_text
    def process_all_text
      IATraductoraVXACE.around_native($game_message.texts) { ia_vxace_original_process_all_text }
    end

    alias_method :ia_vxace_original_input_choice, :input_choice
    def input_choice
      IATraductoraVXACE.around_native($game_message.choices) { ia_vxace_original_input_choice }
    end
  end
end

# Scroll text runs on the main update loop, not the message fiber.
if defined?(Window_ScrollText) && Window_ScrollText.method_defined?(:start_message)
  class Window_ScrollText
    alias_method :ia_vxace_original_scroll_start, :start_message
    def start_message
      array = $game_message.texts
      if !@ia_scroll_plan || @ia_scroll_source != array
        @ia_scroll_source = array.dup
        @ia_scroll_plan = IATraductoraVXACE.plan(@ia_scroll_source)
      end
      return unless IATraductoraVXACE.advance(@ia_scroll_plan)
      original = @ia_scroll_source
      translated = IATraductoraVXACE.result(@ia_scroll_plan)
      @ia_scroll_plan = @ia_scroll_source = nil
      array.replace(translated)
      begin
        ia_vxace_original_scroll_start
      ensure
        array.replace(original) if array == translated
      end
    end
  end
end

# F10 is an explicitly requested diagnostic only, never a translation overlay.
if defined?(Window_Base) && defined?(Scene_Map)
  class Window_IAVXACEDiagnostics < Window_Base
    def initialize
      super(8, 8, 380, 128)
      self.visible = false
      self.z = 9999
    end
    def refresh
      contents.clear
      lines = ['IA Traductora - VX Ace',
               'Estado: ' + IATraductoraVXACE.status.to_s,
               'Solicitudes: ' + IATraductoraVXACE.requests.to_s,
               'Traducidas: ' + IATraductoraVXACE.translated.to_s,
               'Fallidas: ' + IATraductoraVXACE.failures.to_s]
      lines.each_with_index { |line,i| contents.draw_text(0,i*20,contents.width,20,line) }
    end
  end
  class Scene_Map
    alias_method :ia_vxace_original_start, :start
    def start
      ia_vxace_original_start
      @ia_vxace_diagnostics = Window_IAVXACEDiagnostics.new
      @ia_vxace_tick = 0
    end
    alias_method :ia_vxace_original_update, :update
    def update
      ia_vxace_original_update
      if @ia_vxace_diagnostics
        if IATraductoraVXACE.f10?
          @ia_vxace_diagnostics.visible = !@ia_vxace_diagnostics.visible
          @ia_vxace_diagnostics.refresh if @ia_vxace_diagnostics.visible
        end
        @ia_vxace_tick += 1
        @ia_vxace_diagnostics.refresh if @ia_vxace_diagnostics.visible && @ia_vxace_tick % 30 == 0
      end
    end
    alias_method :ia_vxace_original_terminate, :terminate
    def terminate
      @ia_vxace_diagnostics.dispose if @ia_vxace_diagnostics && !@ia_vxace_diagnostics.disposed?
      ia_vxace_original_terminate
    end
  end
end
IATraductoraVXACE.start
