# encoding: UTF-8
# IA_TRADUCTORA_VXACE_RGSS3_OWNER_V1
# Servidor / Ruby 1.9.2 core-only adapter. No socket, JSON, gems or overlay.
# The verified native helper launches the same game-local OPUS worker.
module IATraductoraVXACE
  PLUGIN_BUILD = 'VXACE-RGSS3-20261126-F'
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

    def startup_helper_code
      raw = bounded_read(local("vxace-startup-helper-#{Process.pid}.txt"), 512)
      code = raw && raw.strip
      code && code =~ /\AIA_[A-Z0-9_]{4,90}\z/ ? code : nil
    rescue StandardError
      nil
    end

    def launch_diagnostic
      # Only status categories; never read/display tokens or dialogue.
      helper = startup_helper_code || @launch_error || 'IA_VXACE_LAUNCH_NOT_REPORTED'
      raw = bounded_read(local("vxace-startup-worker-#{Process.pid}.json"), 1024)
      worker = raw && raw[/"code"\s*:\s*"(IA_[A-Z0-9_]{4,90})"/, 1]
      helper + ' / ' + (worker || 'IA_VXACE_WORKER_NOT_REPORTED')
    rescue StandardError
      'IA_VXACE_LAUNCH_DIAGNOSTIC_UNAVAILABLE'
    end

    def start
      return if @started
      @started = true
      # A session already bound to this process takes precedence. Starting
      # another helper here can fail unnecessarily (including a live worker).
      return if session
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
        # Explicit executable/argv0 tuple: do not let Ruby split a Unicode
        # path containing spaces or invoke a command interpreter.
        pid = Process.spawn([helper, helper], 'launch-worker', '--parent-pid', Process.pid.to_s,
                            :chdir => root, :out => File::NULL, :err => File::NULL)
        @launch_process = Process.detach(pid)
      end
    rescue StandardError => error
      @launch_error = case error
      when Errno::ENOENT then 'IA_VXACE_HELPER_NO_ENCONTRADO'
      when Errno::EACCES then 'IA_VXACE_HELPER_ACCESO_DENEGADO'
      when ArgumentError, EncodingError then 'IA_VXACE_HELPER_ARGUMENTO_INVALIDO'
      else
        error.message == 'IA_VXACE_HELPER' ? 'IA_VXACE_HELPER_NO_VERIFICADO' : 'IA_VXACE_HELPER_LAUNCH_FAILED'
      end
      @status = 'OPUS no disponible: ' + @launch_error
    end

    def launch_failed?
      return false if session
      return true if @launch_error
      if @launch_process && !@launch_process.alive?
        return true unless @launch_process.value.success?
      end
      code = startup_helper_code
      code && !['IA_VXACE_LAUNCH_CHECKING', 'IA_VXACE_WORKER_SPAWNED'].include?(code)
    rescue StandardError
      false
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
          next if j.odd? || !piece.is_a?(String)
          next unless piece.dup.force_encoding('UTF-8').valid_encoding?
          piece = piece.dup.force_encoding('UTF-8')
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

    def finish_unavailable(p)
      @failures += p[:queue].inject(0) { |n,keys| n + keys.length }
      @failures += p[:active][3].length if p[:active]
      p[:queue].clear
      p[:active] = nil
      @status = 'Original conservado: ' + launch_diagnostic
      true
    end

    def advance(p)
      return true if p[:queue].empty? && !p[:active]
      return finish_unavailable(p) if Time.now.to_f >= p[:deadline]
      return false if Time.now.to_f < p[:next_poll]
      p[:next_poll] = Time.now.to_f + 0.04

      # Consume an already published answer before consulting launcher errors.
      # A failed launcher is not evidence that an active session has failed.
      if p[:active]
        unless receive_batch(p)
          return finish_unavailable(p) if launch_failed?
          return false
        end
      end
      return true if p[:queue].empty?
      descriptor = session
      unless descriptor
        start
        descriptor = session
        return finish_unavailable(p) if !descriptor && launch_failed?
        return false unless descriptor
      end
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
      original = array.map { |s| s.is_a?(String) ? s.dup : s }
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

  # Native presentation only: do not modify RPG database names, command
  # symbols, event lists, equipment IDs, user input or save contents.
  UI_TERMS = {
    'magic/item'=>'Magia/Objetos', 'collection'=>'Colección',
    'gear'=>'Equipo', 'check self'=>'Estado', 'order'=>'Orden',
    'memory'=>'Recuerdos', 'exit game'=>'Salir del juego',
    'recruit'=>'Recluta', 'age'=>'Edad', 'current exp'=>'EXP actual',
    'to next age'=>'Siguiente edad', 'physical'=>'Físico',
    'cunning'=>'Astucia', 'magic'=>'Magia', 'intellect'=>'Intelecto',
    'charm'=>'Encanto', 'empathy'=>'Empatía', 'knife'=>'Cuchillo',
    'light brace'=>'Brazal ligero', 'magic cloak'=>'Capa mágica',
    'gifts'=>'Regalos', 'clothes'=>'Ropa', 'tokens'=>'Fichas',
    'item'=>'Objeto', 'items'=>'Objetos', 'skill'=>'Habilidad',
    'skills'=>'Habilidades', 'equip'=>'Equipar', 'equipment'=>'Equipo',
    'status'=>'Estado', 'save'=>'Guardar', 'load'=>'Cargar',
    'continue'=>'Continuar', 'new game'=>'Nueva partida',
    'game end'=>'Salir', 'options'=>'Opciones', 'cancel'=>'Cancelar',
    'yes'=>'Sí', 'no'=>'No', 'attack'=>'Atacar', 'guard'=>'Defender',
    'fight'=>'Luchar', 'escape'=>'Huir', 'level'=>'Nivel',
    'weapon'=>'Arma', 'armor'=>'Armadura', 'accessory'=>'Accesorio',
    'gold'=>'Oro', 'health'=>'Salud', 'experience'=>'Experiencia'
  }
  UI_OUTPUTS = UI_TERMS.values
  @ui_cache = {}
  @ui_pending = {}
  @ui_retry = {}
  @ui_refresh = []
  @ui_active = nil
  @ui_next_tick = 0.0
  @hud_frames = 0
  @hud_open = false

  class << self
    # Measure what the game will draw, using the current native font. Word
    # wrapping is in pixels rather than a fixed number of characters.
    def glyph_width(bitmap, text)
      width = 0
      text.each_char { |ch| width += bitmap.text_size(ch).width }
      width
    end

    def content_limit(window)
      bitmap = window.contents
      available = bitmap.width
      if window.respond_to?(:contents_width)
        w = window.contents_width
        available = [available, w].min if w.is_a?(Numeric) && w > 0
      end
      [available - 3, 1].max
    rescue StandardError
      nil
    end

    def wrap_raw(window, text, width)
      return text unless text.is_a?(String) && width && width > 4
      bitmap = window.contents
      return text unless bitmap && !bitmap.disposed?
      old_size = bitmap.font.size
      out = ''
      x = 0
      pending = ''
      # Native controls remain complete; line breaks are presentation only.
      tokens = text.scan(/\\(?:[A-Za-z]+(?:\[[^\]\r\n]*\]|<[^>\r\n]*>)?|.)|\r\n|\r|\n|\f|[ \t]+|[^\\\s\f]+|./m)
      tokens.each do |token|
        if token =~ /\A(?:\r\n|\r|\n|\f)\z/
          out << pending << token
          pending = ''
          x = 0
        elsif token =~ /\A[ \t]+\z/
          pending << token
        elsif token[0,1] == '\\'
          # Account for the visible part of icon and variable/name controls.
          visible = nil
          if token =~ /\A\\I\[\d+\]\z/i
            amount = 24
          elsif token == '\\\\'
            amount = glyph_width(bitmap,'\\')
          elsif token =~ /\A\\(?:[VNP]\[\d+\]|G)\z/i && window.respond_to?(:convert_escape_characters)
            visible = window.convert_escape_characters(token)
            amount = glyph_width(bitmap,visible)
          else
            amount = 0
          end
          space = glyph_width(bitmap,pending)
          if amount > 0 && x > 0 && x + space + amount > width
            out << "\n"
            pending = ''
            x = 0
          end
          out << pending << token
          x += glyph_width(bitmap,pending) + amount
          pending = ''
          bitmap.font.size = [bitmap.font.size+8,64].min if token == '\\{'
          bitmap.font.size = [bitmap.font.size-8,8].max if token == '\\}'
        else
          word = glyph_width(bitmap,token)
          space = glyph_width(bitmap,pending)
          if x > 0 && x + space + word > width
            out << "\n"
            x = 0
            pending = ''
          end
          out << pending
          x += glyph_width(bitmap,pending)
          pending = ''
          token.each_char do |ch|
            amount = glyph_width(bitmap,ch)
            if x > 0 && x + amount > width
              out << "\n"
              x = 0
            end
            out << ch
            x += amount
          end
        end
      end
      out << pending
      out
    rescue StandardError
      text
    ensure
      bitmap.font.size = old_size if bitmap && old_size && !bitmap.disposed?
    end

    # The native message parser still owns escape codes, typing speed,
    # pause and page transitions. Only insert a native newline when needed.
    def message_wrap(window, c, text, pos, word_start)
      return :draw unless c.is_a?(String) && text.is_a?(String) && pos.is_a?(Hash)
      return :draw unless pos[:x].is_a?(Numeric) && pos[:new_x].is_a?(Numeric)
      right = content_limit(window)
      return :draw unless right && right > pos[:new_x]
      bitmap = window.contents
      return :draw if c == "\n" || c == "\f" || c.empty?
      if c == "\e"
        width = text =~ /\AI\[\d+\]/i ? 24 : 0
      elsif c =~ /\A[ \t]\z/
        next_word = text[/\A[^\s\e\f]+/] || ''
        width = glyph_width(bitmap,c)
        word = glyph_width(bitmap,next_word)
        if pos[:x] > pos[:new_x] &&
            (pos[:x] + width > right || (word > 0 && word <= right-pos[:new_x] && pos[:x]+width+word > right))
          return text.empty? ? :skip : :wrap_space
        end
      else
        width = glyph_width(bitmap,c)
        if word_start
          word = width + glyph_width(bitmap,text[/\A[^\s\e\f]*/] || '')
          return :wrap if pos[:x] > pos[:new_x] && word <= right-pos[:new_x] && pos[:x]+word > right
        end
      end
      return :wrap if width > 0 && pos[:x] > pos[:new_x] && pos[:x]+width > right
      :draw
    rescue StandardError
      :draw
    end

    def register_contents(window)
      bitmap = window.contents
      bitmap.instance_variable_set(:@ia_vxace_window,window) if bitmap && !bitmap.disposed?
    rescue StandardError
      nil
    end

    def ui_eligible?(window)
      return false unless window
      return false if window.respond_to?(:disposed?) && window.disposed?
      name = window.class.to_s
      return false if name =~ /(?:Name|Password|Keyboard|NumberInput|InputNumber|SaveFile|Window_File|Message|Choice|ScrollText)/
      if defined?(SceneManager) && SceneManager.respond_to?(:scene)
        scene = SceneManager.scene
        return false if scene && scene.class.to_s =~ /Scene_(?:Name|Save|Load|File)/
      end
      true
    rescue StandardError
      false
    end

    def protected_name?(text)
      actors = []
      if defined?($game_party) && $game_party && $game_party.respond_to?(:members)
        actors.concat($game_party.members)
      end
      if defined?($data_actors) && $data_actors.is_a?(Array)
        actors.concat($data_actors.compact)
      end
      actors.any? do |actor|
        [:name,:nickname].any? do |field|
          actor.respond_to?(field) && actor.send(field).is_a?(String) &&
            actor.send(field).strip.downcase == text.strip.downcase
        end
      end
    rescue StandardError
      true
    end

    def ui_local_term(text)
      key = text.strip.downcase
      value = UI_TERMS[key]
      if !value && key =~ /\A(.+?)\s+(\d+(?:[.,]\d+)?)\z/
        word,number = $1,$2
        value = UI_TERMS[word] + ' ' + number if UI_TERMS[word]
      end
      value
    end

    def ui_text(window,text)
      return text unless text.is_a?(String) && text.length >= 2 && text.length <= MAX_TEXT
      return text unless ui_eligible?(window)
      return text unless text.valid_encoding? && source(text) && text =~ /[A-Za-zぁ-ゖァ-ヺ一-龯]/
      return text if text.strip.length < 2 || protected_name?(text)
      return text if UI_OUTPUTS.include?(text) || @ui_cache.values.include?(text)
      term = ui_local_term(text)
      return term if term
      return @ui_cache[text] if @ui_cache.key?(text)
      return text if @ui_retry[text] && @ui_retry[text] > Time.now.to_f
      if @ui_active && @ui_active[:owners].key?(text)
        owners = @ui_active[:owners][text]
      elsif @ui_pending.key?(text)
        owners = @ui_pending[text]
      else
        return text if @ui_pending.size >= 256
        owners = @ui_pending[text.dup] = []
      end
      owners << window unless owners.include?(window) || owners.length >= 12
      text
    rescue StandardError
      text
    end

    def ui_refresh_window(window)
      return unless ui_eligible?(window)
      return if window.respond_to?(:visible) && !window.visible
      return if window.respond_to?(:openness) && window.openness <= 0
      return unless window.respond_to?(:refresh) && window.method(:refresh).arity <= 0
      selected = window.index if window.respond_to?(:index)
      row = window.top_row if window.respond_to?(:top_row)
      window.refresh
      if selected && window.respond_to?(:select) && window.respond_to?(:index) && window.index != selected
        if !window.respond_to?(:item_max) || (selected >= -1 && selected < window.item_max)
          window.select(selected)
        end
      end
      window.top_row = row if row && window.respond_to?(:top_row=) && window.top_row != row
    rescue StandardError
      nil
    end

    def ui_tick
      now = Time.now.to_f
      return if now < @ui_next_tick
      @ui_next_tick = now + 0.04
      if @ui_active && advance(@ui_active[:plan])
        values = result(@ui_active[:plan])
        @ui_active[:keys].each_with_index do |key,i|
          value = values[i]
          if value && value != key
            @ui_cache[key] = value
            @ui_cache.shift while @ui_cache.size > MAX_CACHE
            @ui_active[:owners][key].each do |window|
              @ui_refresh << window unless @ui_refresh.include?(window) || @ui_refresh.length >= 256
            end
          else
            @ui_retry[key] = now + 30
            @ui_retry.shift while @ui_retry.size > MAX_CACHE
          end
        end
        @ui_active = nil
      end
      if !@ui_active && !@ui_pending.empty?
        owners = {}
        @ui_pending.keys.first(6).each { |key| owners[key] = @ui_pending.delete(key) }
        keys = owners.keys
        @ui_active = { :keys=>keys, :owners=>owners, :plan=>plan(keys) }
      end
      # Refresh the owning native window, not a second subtitle surface.
      2.times do
        break if @ui_refresh.empty?
        ui_refresh_window(@ui_refresh.shift)
      end
    rescue StandardError
      nil
    end

    def ui_draw_args(bitmap,args)
      window = bitmap.instance_variable_get(:@ia_vxace_window)
      return [args,nil] unless ui_eligible?(window)
      return [args,nil] if window.instance_variable_get(:@ia_vxace_rich)
      rect = args[0]
      index = rect.respond_to?(:width) && rect.respond_to?(:height) ? 1 : 4
      text = args[index]
      return [args,nil] unless text.is_a?(String) && text.length >= 2
      value = ui_text(window,text)
      return [args,nil] if value == text
      width = index == 1 ? rect.width : args[2]
      height = index == 1 ? rect.height : args[3]
      result = args.dup
      result[index] = value
      return [result,nil] unless width.is_a?(Numeric) && width > 4 && height.is_a?(Numeric) && height > 4
      old = bitmap.font.size
      # Native one-line labels retain their original rectangle and alignment.
      # Prefer fitting by font size; the RGSS bitmap retains its own squeeze.
      while bitmap.font.size > 12 && (bitmap.text_size(value).width > width-2 || bitmap.text_size(value).height > height)
        bitmap.font.size -= 1
      end
      [result,old]
    rescue StandardError
      bitmap.font.size = old if old
      [args,nil]
    end

    def hud_frame
      return unless defined?(Graphics) && defined?(Sprite) && defined?(Bitmap) && defined?(Color)
      return unless Graphics.width > 40 && Graphics.height > 40
      @hud_frames += 1
      if !@hud_sprite || @hud_sprite.disposed?
        @hud_sprite = Sprite.new
        @hud_sprite.z = 32000
        @hud_signature = nil
      end
      @hud_open = !@hud_open if f10?
      if @hud_frames % 30 == 1
        @hud_session_ready = !!session
        @hud_signature = nil
      end
      width = [@hud_open ? 300 : 186, Graphics.width-12].min
      height = @hud_open ? [112, Graphics.height-12].min : 26
      signature = [width,height,@hud_open,@hud_session_ready,@hud_open ? [@status,@requests,@translated,@failures] : nil]
      if signature != @hud_signature
        bitmap = @hud_sprite.bitmap
        if !bitmap || bitmap.disposed? || bitmap.width != width || bitmap.height != height
          bitmap.dispose if bitmap && !bitmap.disposed?
          @hud_sprite.bitmap = Bitmap.new(width,height)
        end
        bitmap = @hud_sprite.bitmap
        bitmap.clear
        bitmap.fill_rect(0,0,width,height,Color.new(172,148,91,225))
        bitmap.fill_rect(1,1,width-2,height-2,Color.new(15,20,30,224))
        bitmap.font.size = 16
        bitmap.font.color = Color.new(255,255,255)
        bitmap.draw_text(4,0,width-8,26,'◆ IA Traductora · F10',1)
        if @hud_open
          bitmap.font.size = 15
          state = @hud_session_ready ? 'OPUS activo' : 'OPUS iniciando / no disponible'
          bitmap.draw_text(8,28,width-16,19,state)
          bitmap.draw_text(8,48,width-16,19,"Solicitudes: #{@requests} | Traducidas: #{@translated}")
          bitmap.draw_text(8,68,width-16,19,"Fallidas: #{@failures} | Menús: #{@ui_cache.size}")
          bitmap.draw_text(8,88,width-16,19,'F10: cerrar diagnóstico')
        end
        @hud_signature = signature
      end
      @hud_sprite.x = Graphics.width-width-6
      @hud_sprite.y = 6
      @hud_sprite.visible = true
    rescue StandardError
      nil
    end

    def presentation_frame
      ui_tick
      hud_frame
    rescue StandardError
      nil
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
      @ia_vxace_word_start = true
      @ia_vxace_wrap = true
      IATraductoraVXACE.around_native($game_message.texts) { ia_vxace_original_process_all_text }
    ensure
      @ia_vxace_wrap = false
    end

    if method_defined?(:process_character) && method_defined?(:process_new_line)
      alias_method :ia_vxace_original_process_character, :process_character
      def process_character(c,text,pos)
        if @ia_vxace_wrap
          action = IATraductoraVXACE.message_wrap(self,c,text,pos,@ia_vxace_word_start)
          if action == :wrap_space || action == :skip
            process_new_line(text,pos) if action == :wrap_space
            @ia_vxace_word_start = true
            return
          elsif action == :wrap
            # Supply the current glyph in the lookahead so the original
            # page routine sees pending text even for the last glyph.
            process_new_line(c+text,pos)
          end
          @ia_vxace_word_start = !!(c =~ /[\s\e\f]/)
        end
        ia_vxace_original_process_character(c,text,pos)
      end
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
      if respond_to?(:contents) && contents && !contents.disposed?
        width = IATraductoraVXACE.content_limit(self)
        translated = translated.map { |line| IATraductoraVXACE.wrap_raw(self,line,width && width-8) }
      end
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

# Hook only window-owned bitmaps. A custom window drawing directly on its
# contents gets the same presentation path as a standard command window.
if defined?(Window_Base)
  class Window_Base
    if method_defined?(:create_contents)
      alias_method :ia_vxace_create_contents, :create_contents
      def create_contents(*args,&block)
        value = ia_vxace_create_contents(*args,&block)
        IATraductoraVXACE.register_contents(self)
        value
      end
    end
    if method_defined?(:contents=)
      alias_method :ia_vxace_set_contents, :contents=
      def contents=(bitmap)
        value = ia_vxace_set_contents(bitmap)
        IATraductoraVXACE.register_contents(self)
        value
      end
    end
    if method_defined?(:draw_text)
      alias_method :ia_vxace_window_draw_text, :draw_text
      def draw_text(*args,&block)
        IATraductoraVXACE.register_contents(self)
        ia_vxace_window_draw_text(*args,&block)
      end
    end
    if method_defined?(:draw_text_ex)
      alias_method :ia_vxace_draw_text_ex, :draw_text_ex
      def draw_text_ex(x,y,text,*args,&block)
        IATraductoraVXACE.register_contents(self)
        old = @ia_vxace_rich
        @ia_vxace_rich = true
        translated = IATraductoraVXACE.ui_text(self,text)
        if translated != text && self.class.to_s =~ /Help/ && x.is_a?(Numeric)
          width = IATraductoraVXACE.content_limit(self)
          translated = IATraductoraVXACE.wrap_raw(self,translated,width && width-x)
        end
        ia_vxace_draw_text_ex(x,y,translated,*args,&block)
      ensure
        @ia_vxace_rich = old
      end
    end
  end
end

if defined?(Bitmap) && Bitmap.method_defined?(:draw_text)
  class Bitmap
    alias_method :ia_vxace_bitmap_draw_text, :draw_text
    def draw_text(*args,&block)
      converted,old_size = IATraductoraVXACE.ui_draw_args(self,args)
      ia_vxace_bitmap_draw_text(*converted,&block)
    ensure
      font.size = old_size if old_size && !disposed?
    end
  end
end

# A small status badge (not a translation overlay) survives native scene
# changes. F10 is still focus-checked by the existing Win32 key handler.
if defined?(Graphics) && Graphics.respond_to?(:update)
  class << Graphics
    alias_method :ia_vxace_graphics_update, :update
    def update(*args,&block)
      value = ia_vxace_graphics_update(*args,&block)
      IATraductoraVXACE.presentation_frame
      value
    end
  end
end
IATraductoraVXACE.start
