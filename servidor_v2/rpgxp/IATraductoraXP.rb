# IA_TRADUCTORA_RPGXP_RGSS1_OWNER_V1
# RGSS1 / Ruby 1.8. A presentation adapter, not an installer.
# No Fiber, String#encode, encoding metadata, native overlay or eval.
# A separately verified transport supplies poll(lang, text). Until one
# is attached, native messages continue unchanged.
module IATraductoraXP
  BUILD = 'RPGXP-RGSS1-R43-LAB-2'
  PRESENTATION_REVISION = 'R43-XP-COVERAGE-1'
  MAX_WAIT = 12.0
  MAX_CACHE = 4096
  MAX_BYTES = 7200
  CONTROL = /(\\\\|\\[vncVNC]\[[0-9]+\]|\\[gG](?![A-Za-z])|\r\n|\r|\n|%[0-9]+|%[sd]|\{[A-Za-z_][A-Za-z0-9_]*\})/
  @cache = {}
  @order = []
  @transport = nil

  # File-only transport for old Ruby, no sockets, JSON, gems or external
  # services. Lab callers attach it explicitly after the worker starts.
  class FileBridge
    SIDECAR=File.join('IA Traductora','.local','Rpg')
    LIMIT=96*1024
    def initialize
      @cwd=Dir.pwd
      @token=nil
      @serial=0
      @pending={}
      @rejected={}
    end
    def safe_dir(path)
      current='.'
      path.split('/').each do |part|
        return false if part.empty? || part=='.' || part=='..'
        current=File.join(current,part)
        return false if File.symlink?(current) || !File.directory?(current)
      end
      true
    end
    def read(path,limit)
      return nil if File.symlink?(path) || !File.file?(path) || File.size(path)>limit
      value=File.open(path,'rb') { |f| f.read(limit+1) }
      value && value.length<=limit ? value : nil
    rescue StandardError
      nil
    end
    def session
      return nil unless Dir.pwd==@cwd && safe_dir(SIDECAR)
      raw=read(File.join(SIDECAR,'rpgxp-session.txt'),512)
      return nil unless raw
      fields=raw.split("\n")
      return nil unless fields.length==4 && fields[0]=='IA-RPGXP-SESSION-1' &&
        fields[1] =~ /\A[0-9a-f]{64}\z/ && fields[2] =~ /\A[1-9][0-9]*\z/ &&
        fields[3]==Process.pid.to_s
      directory=File.join(SIDECAR,'rpgxp-ipc',fields[1])
      return nil unless safe_dir(directory)
      [fields[1],directory]
    rescue StandardError
      nil
    end
    def poll(lang,text)
      return nil unless (lang=='ja' || lang=='en') && text.is_a?(String) &&
        text.length<=MAX_BYTES && IATraductoraXP.codepoints(text)
      descriptor=session
      return nil unless descriptor
      token,dir=descriptor
      if @token!=token
        @token=token
        @serial=0
        @pending.clear
        @rejected.clear
      end
      key=[lang,text]
      return nil if @rejected.has_key?(key)
      now=Time.now.to_f
      @pending.delete_if { |k,v| now-v[2]>60.0 }
      old=@pending[key]
      if old
        file=old[0]+'.res'
        raw=read(file,LIMIT)
        return nil unless raw
        lines=raw.split("\n")
        File.delete(file) unless File.symlink?(file)
        @pending.delete(key)
        if lines.length==4 && lines[0]=='IA-RPGXP-RESPONSE-1' && lines[1]==token &&
            lines[2]==old[1] && lines[3] =~ /\A(?:[0-9a-f]{2})+\z/
          value=[lines[3]].pack('H*')
          points=IATraductoraXP.codepoints(value)
          return points.pack('U*') if points && IATraductoraXP.valid?(lang,text,value)
        end
        @rejected.clear if @rejected.size>=4096
        @rejected[key]=true
        return nil
      end
      return nil if @pending.size>=32
      @serial+=1
      ident=sprintf('%016x',@serial)
      base=File.join(dir,ident)
      return nil if File.exist?(base+'.req') || File.exist?(base+'.res') || File.symlink?(base+'.req') || File.symlink?(base+'.res')
      temp=base+'.tmp'
      created=false
      begin
        payload=['IA-RPGXP-REQUEST-1',token,lang,text.unpack('H*')[0]].join("\n")+"\n"
        return nil if payload.length>LIMIT
        File.open(temp,File::WRONLY|File::CREAT|File::EXCL|File::BINARY) do |f|
          created=true
          f.write(payload)
        end
        File.rename(temp,base+'.req')
        @pending[key]=[base,ident,now]
      ensure
        File.delete(temp) if created && File.file?(temp) && !File.symlink?(temp)
      end
      nil
    rescue StandardError
      nil
    end
  end
  class << self
    def attach(transport)
      @transport = transport
    end
    def wide_ascii(text)
      (text.unpack('C*')+[0]).pack('v*')
    end
    def fold_path(units)
      units.map { |u| u>=65 && u<=90 ? u+32 : (u==47 ? 92 : u) }
    end
    def start_native
      return false unless defined?(Win32API) && defined?(Window_Message)
      return false if @transport
      # Resolve the actual executable, not an arbitrary CWD. Check that the
      # game's existing relative file access is rooted in the same directory.
      module_api=Win32API.new('kernel32','GetModuleFileNameW','lpl','l')
      full_api=Win32API.new('kernel32','GetFullPathNameW','plpl','l')
      buffer="\0"*65536
      count=module_api.call(0,buffer,32768)
      return false unless count>0 && count<32768
      executable=buffer[0,count*2].unpack('v*')
      candidate="\0"*65536
      n=full_api.call(wide_ascii('Game.exe'),32768,candidate,0)
      return false unless n>0 && n<32768 && fold_path(executable)==fold_path(candidate[0,n*2].unpack('v*'))
      separator=executable.rindex(92)
      return false unless separator && fold_path(executable[separator+1..-1])=='game.exe'.unpack('C*')
      root=executable[0...separator]
      # Keep all native launch paths in UTF-16. No shell, no Ruby 1.9 APIs.
      helper=File.join('IA Traductora','.local','Rpg','engine','rpgxp-launcher.exe')
      return false unless File.file?(helper) && !File.symlink?(helper)
      transport=FileBridge.new
      if transport.session
        attach(transport);return true
      end
      shell=Win32API.new('shell32','ShellExecuteW','lppppl','l')
      suffix=('\IA Traductora\.local\Rpg\engine\rpgxp-launcher.exe').unpack('C*')
      path=(root+suffix+[0]).pack('v*')
      result=shell.call(0,wide_ascii('open'),path,wide_ascii('--xp-launch-parent '+Process.pid.to_s),(root+[0]).pack('v*'),0)
      return false unless result>32
      attach(transport)
      true
    rescue StandardError
      false
    end
    def codepoints(value)
      points = value.unpack('U*')
      return nil if points.any? { |c| c > 0x10ffff || (c >= 0xd800 && c <= 0xdfff) }
      return nil unless points.pack('U*').unpack('C*') == value.unpack('C*')
      points
    rescue StandardError
      nil
    end
    def japanese?(value)
      points = codepoints(value)
      points && points.any? { |c| (c >= 0x3041 && c <= 0x30ff) || (c >= 0x3400 && c <= 0x9fff) || (c >= 0xff66 && c <= 0xff9d) }
    end
    # Names are identity, not UI vocabulary. The original database is read
    # only; no actor, enemy, item or event record is ever changed.
    def identity?(value)
      text=value.strip.sub(/:\z/,'')
      groups=[]
      groups.push($data_actors) if defined?($data_actors) && $data_actors.is_a?(Array)
      groups.push($data_enemies) if defined?($data_enemies) && $data_enemies.is_a?(Array)
      stamp=groups.map { |g| [g.object_id,g.size] }
      if @identity_stamp!=stamp
        @identity_stamp=stamp
        @identities={}
        groups.each do |g|
          g[0,20000].each do |item|
            @identities[item.name]=true if item && item.respond_to?(:name) && item.name.is_a?(String)
          end
        end
      end
      return true if @identities && @identities.has_key?(text)
      if defined?($game_party) && $game_party && $game_party.respond_to?(:actors)
        return true if $game_party.actors.any? { |actor| actor && actor.respond_to?(:name) && actor.name==text }
      end
      false
    rescue StandardError
      false
    end
    def term?(value)
      groups=[]
      groups.push($data_classes) if defined?($data_classes) && $data_classes.is_a?(Array)
      groups.push($data_states) if defined?($data_states) && $data_states.is_a?(Array)
      groups.push($data_items) if defined?($data_items) && $data_items.is_a?(Array)
      groups.push($data_skills) if defined?($data_skills) && $data_skills.is_a?(Array)
      groups.push($data_weapons) if defined?($data_weapons) && $data_weapons.is_a?(Array)
      groups.push($data_armors) if defined?($data_armors) && $data_armors.is_a?(Array)
      stamp=groups.map { |g| [g.object_id,g.size] }
      if @term_stamp!=stamp
        @term_stamp=stamp
        @terms={}
        groups.each do |g|
          g[0,20000].each do |item|
            @terms[item.name]=true if item && item.respond_to?(:name) && item.name.is_a?(String)
          end
        end
      end
      @terms && @terms.has_key?(value.strip)
    rescue StandardError
      false
    end
    def source(value,mode=:message)
      points=codepoints(value)
      return nil if !points || points.length>1800 || value =~ /[\x00-\x1f\\<>]/
      return nil if identity?(value)
      return 'ja' if japanese?(value)
      # Fold typographical punctuation for detection only, not the model
      # request or original event. Do not classify binary/unknown encodings.
      return nil if points.any? { |n| n>127 && !(n>=0xc0 && n<=0x24f) && ![0x2013,0x2014,0x2018,0x2019,0x201c,0x201d,0x2026,0xa0].include?(n) }
      plain=points.map do |n|
        case n
        when 0x2018,0x2019 then 39
        when 0x201c,0x201d then 34
        when 0x2013,0x2014 then 45
        when 0x2026 then 46
        when 0xa0 then 32
        else n
        end
      end.pack('U*')
      return nil if plain =~ /\A(?:[A-Za-z0-9_]+\.[A-Za-z0-9]+|[A-Z0-9_]{2,})\z/ || plain =~ /https?:|www\.|[A-Za-z]:[\/\\]/
      words=plain.scan(/[A-Za-z]+/)
      return nil if words.empty?
      english=plain =~ /\b(?:a|an|the|i|me|my|mine|you|your|he|she|him|her|they|them|we|us|our|it|its|am|is|are|was|were|be|been|being|do|does|did|not|no|can|could|will|would|should|must|may|might|have|has|had|of|to|for|from|and|but|or|in|on|at|by|with|without|as|out|up|down|into|over|under|about|after|before|when|then|where|what|which|who|why|how|this|that|these|those|here|there|please|hear|listen|wait|look|help|come|go|open|close|thank|oh|lord|perhaps|now|still|never|ever|always|once|long|ago|years|attention|continue|press|button|next|previous|chapter|story|quest|good|morning|night|welcome|sorry|really|enough|something|nothing|everything|already|again|back|away|new|old|ready|take|give|find|need|want|remember|together|until|because|since|while)\b/i
      spanish=plain =~ /\b(?:usted|ustedes|nosotros|vosotros|ellos|ellas|tienes|tiene|tengo|puedes|puede|quiero|gracias|buenos|buenas|hola|espera|cierra|abre|para|porque|pero|del|desde|hacia|sobre|tambien|entonces|ahora|esto|esta|estos|estas|muchas|muchos|donde|cuando|como|unas|unos|una|uno|los|las|que|por|con|sin|el|la)\b/i
      # Colon-only headings are often proper names. Translate recognizable
      # generic occupations and descriptive roles, not arbitrary names.
      role=plain =~ /\b(?:guard|merchant|shopkeeper|villager|soldier|traveler|traveller|beggar|homeless|praying|priest|priestess|innkeeper|blacksmith|sailor|farmer|stranger|child|elder|narrator|worker|captain|officer|clerk|librarian)\b/i
      if plain =~ /\A[^.!?\r\n]+:\z/
        return 'en' if role && !spanish
        return nil unless mode==:term
      end
      return nil if spanish && !english
      return 'en' if mode==:term && words.size>=1 && plain !~ /\A[0-9\s[:punct:]]+\z/
      return 'en' if words.size>=2 && (english || role)
      # In an event message, an ordinary lowercase sentence fragment with
      # punctuation is useful prose even without a fixed stopword list.
      return 'en' if mode==:message && words.size>=2 && !spanish &&
        words.any? { |w| w =~ /\A[a-z]{3,}\z/ } && plain =~ /[.!?,;]/
      return 'en' if plain =~ /\A(?:yes|cancel|continue|attack|defend|save|load|exit|wait|help|hello|thanks|attention|welcome|sorry|stop|run|look|listen|leave|return|ready|goodbye)[.!?]?\z/i
      nil
    rescue StandardError
      nil
    end
    def signature(value)
      points=codepoints(value)
      return nil unless points
      normalized=points.map { |c| c>=0xff10 && c<=0xff19 ? c-0xff10+48 : c }.pack('U*')
      normalized.scan(/[0-9]+/).map { |n| n.sub(/\A0+(?=[0-9])/,'') }.sort
    end
    def valid?(lang, original, value)
      return false unless value.is_a?(String) && value.length<=MAX_BYTES && codepoints(value)
      return false if value.strip.empty? || value==original || value =~ /[\x00-\x1f\\<>{}]|%[0-9sd]/
      return false if lang=='ja' && japanese?(value)
      return false unless signature(original)==signature(value)
      true
    end
    def remember(key,value)
      return if @cache.has_key?(key)
      @cache[key]=value
      @order.push(key)
      @cache.delete(@order.shift) while @order.length>MAX_CACHE
    end
    def plan(raw,mode=:message)
      return nil unless @transport && raw.is_a?(String) && raw.length<=MAX_BYTES && codepoints(raw)
      pieces=raw.split(CONTROL,-1)
      # Unknown control syntax is not prose. Preserve this whole message.
      pieces.each_with_index do |piece,i|
        return nil if i%2==0 && piece =~ /[\\\x00-\x1f<>]/
      end
      entries=[]
      original_pieces=pieces.dup
      line=0
      lines=[]
      pieces.each_with_index do |piece,i|
        lines[i]=line
        line+=1 if i%2==1 && (piece=="\n" || piece=="\r" || piece=="\r\n")
        next if i%2==1
        lead=piece[/\A[ \t]*/] || ''
        tail=piece[/[ \t]*\z/] || ''
        next if lead.length+tail.length>=piece.length
        body=piece[lead.length,piece.length-lead.length-tail.length]
        lang=source(body,mode)
        next unless lang
        key=[lang,body]
        if @cache.has_key?(key)
          pieces[i]=lead+@cache[key]+tail
        else
          entries.push([i,key,lead,tail])
        end
      end
      {:pieces=>pieces,:original=>original_pieces,:lines=>lines,:entries=>entries,:until=>Time.now.to_f+MAX_WAIT}
    rescue StandardError
      nil
    end
    def advance(p)
      return true if !p || p[:entries].empty?
      return true if Time.now.to_f>=p[:until]
      p[:entries].delete_if do |item|
        i,key,lead,tail=item
        value=@cache[key]
        value=@transport.poll(key[0],key[1]) unless value
        if value && valid?(key[0],key[1],value)
          remember(key,value)
          p[:pieces][i]=lead+value+tail
          true
        else
          false
        end
      end
      p[:entries].empty?
    rescue StandardError
      true
    end
    def render(p,raw,choice_start=nil)
      return raw unless p
      pieces=p[:pieces].dup
      # Keep every ready dialogue line even when a different line timed
      # out. Choices remain atomic: unresolved choices revert as a group.
      if choice_start && p[:entries].any? { |entry| p[:lines][entry[0]]>=choice_start }
        pieces.each_index do |i|
          pieces[i]=p[:original][i] if p[:lines][i]>=choice_start
        end
      end
      pieces.join
    end
    def choice_boundary
      if $game_temp.respond_to?(:choice_max) && $game_temp.choice_max.to_i>0 && $game_temp.respond_to?(:choice_start)
        return $game_temp.choice_start.to_i
      end
      nil
    end
    def session_active?
      return false unless @transport
      !@transport.respond_to?(:session) || !!@transport.session
    rescue StandardError
      false
    end
    def fit_message(window,shown)
      return nil unless window.respond_to?(:contents)
      bitmap=window.contents
      return nil unless bitmap && !bitmap.disposed?
      font=bitmap.font
      old=font.size
      return nil unless old.is_a?(Numeric) && old>12
      lines=shown.split(/\r\n|\r|\n/).map { |s| s.gsub(/\\[vncVNC]\[[0-9]+\]|\\[gG]/,'') }
      limit=bitmap.width-16
      return nil unless limit>32
      widest=lines.map { |s| bitmap.text_size(s).width }.max || 0
      return nil unless widest>limit
      size=[12,(old*limit.to_f/widest).floor].max
      font.size=size if size<old
      size<old ? [font,old] : nil
    rescue StandardError
      nil
    end
    def pending_message
      return nil unless defined?($game_temp) && $game_temp &&
        $game_temp.respond_to?(:message_text) && $game_temp.respond_to?(:message_text=)
      raw=$game_temp.message_text
      return nil unless raw.is_a?(String) && !raw.empty?
      return nil if $game_temp.respond_to?(:num_input_variable_id) && $game_temp.num_input_variable_id.to_i>0
      raw
    end
  end
end

# XP's ordinary Window_Message draws $game_temp.message_text (including
# choices) in refresh, after update accepts a pending message. Do not call
# the renderer twice, create a Window, alter choice callbacks, or edit events.
if defined?(Window_Message) && Window_Message.method_defined?(:update) &&
    Window_Message.method_defined?(:refresh) && !Window_Message.method_defined?(:ia_xp_original_update)
  class Window_Message
    alias_method :ia_xp_original_update, :update
    alias_method :ia_xp_original_refresh, :refresh
    def update(*args,&block)
      raw=IATraductoraXP.pending_message
      # Only the verified stock-style idle window is eligible. Unknown
      # custom multi-window states keep the original implementation.
      idle=(@contents_showing==false && !@fade_in && !@fade_out)
      if raw && idle
        if !@ia_xp_pending || !@ia_xp_pending[0].equal?(raw) || @ia_xp_pending[1]!=raw
          @ia_xp_pending=[raw,raw.dup,IATraductoraXP.plan(raw)]
        end
        return unless IATraductoraXP.advance(@ia_xp_pending[2])
      else
        @ia_xp_pending=nil
      end
      ia_xp_original_update(*args,&block)
    end
    def refresh(*args,&block)
      raw=IATraductoraXP.pending_message
      pending=@ia_xp_pending
      @ia_xp_pending=nil
      return ia_xp_original_refresh(*args,&block) unless raw && pending &&
        pending[0].equal?(raw) && pending[1]==raw
      shown=IATraductoraXP.render(pending[2],raw,IATraductoraXP.choice_boundary)
      return ia_xp_original_refresh(*args,&block) if shown==raw
      # The stock XP refresh destructively consumes its input String.
      # Give it a temporary copy; restore only if it still owns that copy.
      projected=shown.dup
      $game_temp.message_text=projected
      fitted=nil
      begin
        fitted=IATraductoraXP.fit_message(self,shown)
        ia_xp_original_refresh(*args,&block)
      ensure
        fitted[0].size=fitted[1] if fitted
        $game_temp.message_text=raw if $game_temp.message_text.equal?(projected)
      end
    end
  end
end


# RGSS1 native UI coverage. Only registered Window_Base contents are eligible.
# No global image replacement, event mutation, scene restart or text overlay.
module IATraductoraXPUI
  LABELS={
    'New Game'=>'Nueva partida','New Quest'=>'Nueva aventura','Continue'=>'Continuar',
    'End Game'=>'Salir','Item'=>'Objetos','Items'=>'Objetos','Skill'=>'Habilidades',
    'Skills'=>'Habilidades','Equip'=>'Equipo','Equipment'=>'Equipo',
    'Status'=>'Estado','Save'=>'Guardar','Load'=>'Cargar','Quit'=>'Salir',
    'Exit'=>'Salir','Cancel'=>'Cancelar','Yes'=>'Sí','No'=>'No',
    'Play Time'=>'Tiempo de juego','Step Count'=>'Pasos','Level'=>'Nivel',
    'Level:'=>'Nivel:','[Normal]'=>'[Normal]','Normal'=>'Normal',
    'Attack'=>'Atacar','Defend'=>'Defender','Guard'=>'Defender','Escape'=>'Huir',
    'Fight'=>'Luchar','Buy'=>'Comprar','Sell'=>'Vender','Weapon'=>'Arma',
    'Armor'=>'Armadura','Head'=>'Cabeza','Body'=>'Cuerpo','Accessory'=>'Accesorio',
    'Sub Arms'=>'Arma secundaria','Gold'=>'Oro','Gained'=>'Obtenido',
    'LEVEL UP!'=>'¡SUBE DE NIVEL!','Quest'=>'Misión','Quest:'=>'Misión:',
    'Quests'=>'Misiones','Quest Log'=>'Misiones','Journal'=>'Diario',
    'Reward:'=>'Recompensa:','Location:'=>'Ubicación:','Completion:'=>'Progreso:',
    'Completed'=>'Completado','In Progress'=>'En curso','Description:'=>'Descripción:',
    'Price:'=>'Precio:','Owned:'=>'En posesión:','Cannot Equip'=>'No equipable',
    'No Change'=>'Sin cambios','Currently Equipped'=>'Equipado',
    'Required Material:'=>'Material necesario:','Salvaged Material:'=>'Material recuperado:',
    'Achievements'=>'Logros','Crusader'=>'Cruzado'
  }
  @owners={}
  @plans={}
  @jobs=[]
  @serial=0
  @painting=false
  @suppress=0
  @applied=0
  @next_tick=0.0
  @next_badge=0.0
  @details=false
  @key_down=false
  class << self
    attr_reader :applied
    def live?(bitmap)
      bitmap && bitmap.respond_to?(:disposed?) && !bitmap.disposed?
    rescue StandardError
      false
    end
    def allowed?(window)
      return false unless live?(window)
      return false if defined?(Window_Message) && window.is_a?(Window_Message)
      name=window.class.to_s
      name !~ /(?:NameEdit|NameInput|InputNumber|Debug)/
    rescue StandardError
      false
    end
    def register(window,bitmap)
      return unless allowed?(window) && live?(bitmap)
      @owners[bitmap.object_id]=[window,bitmap]
      prune if @owners.size>128
    rescue StandardError
      nil
    end
    def owner(bitmap)
      return nil if @painting || @suppress>0
      pair=@owners[bitmap.object_id]
      return nil unless pair && pair[1].equal?(bitmap) && allowed?(pair[0]) &&
        live?(bitmap) && pair[0].contents.equal?(bitmap)
      pair[0]
    rescue StandardError
      nil
    end
    def without_translation
      @suppress+=1
      yield
    ensure
      @suppress-=1
    end
    def rect_args(args)
      if args[0].respond_to?(:x) && args[0].respond_to?(:width)
        r=args[0]
        return [r.x,r.y,r.width,r.height]
      end
      return args[0,4] if args.size>=4 && args[0,4].all? { |v| v.is_a?(Numeric) }
      nil
    rescue StandardError
      nil
    end
    def overlap?(a,b)
      !a || !b || (a[0]<b[0]+b[2] && b[0]<a[0]+a[2] && a[1]<b[1]+b[3] && b[1]<a[1]+a[3])
    end
    def drop(job)
      @jobs.delete(job)
      snap=job[:snapshot]
      snap.dispose if live?(snap)
    rescue StandardError
      nil
    end
    def invalidate(bitmap,rect=nil)
      return if @painting || @jobs.empty?
      @jobs.dup.each { |job| drop(job) if job[:bitmap].equal?(bitmap) && overlap?(job[:rect],rect) }
    rescue StandardError
      nil
    end
    def mutation(bitmap,kind,args)
      return if @painting || @jobs.empty?
      rect=nil
      case kind
      when :fill_rect,:clear_rect,:stretch_blt then rect=rect_args(args)
      when :blt
        if args.size>=4 && args[3].respond_to?(:width)
          rect=[args[0],args[1],args[3].width,args[3].height]
        end
      when :set_pixel then rect=[args[0],args[1],1,1]
      end
      invalidate(bitmap,rect)
    rescue StandardError
      invalidate(bitmap)
    end
    def prune
      @owners.delete_if do |key,pair|
        !allowed?(pair[0]) || !live?(pair[1]) || !pair[0].contents.equal?(pair[1])
      end
      @jobs.dup.each { |job| drop(job) unless owner(job[:bitmap]) }
    rescue StandardError
      nil
    end
    def term_mode(text)
      IATraductoraXP.term?(text) ? :term : :ui
    end
    def value(text)
      return text unless text.is_a?(String) && !IATraductoraXP.identity?(text)
      fixed=LABELS[text]
      return fixed if fixed
      p=IATraductoraXP.plan(text,term_mode(text))
      return text unless p && p[:entries].empty?
      IATraductoraXP.render(p,text)
    rescue StandardError
      text
    end
    def font_state(font)
      color=font.color
      [font.name,font.size,font.bold,font.italic,Color.new(color.red,color.green,color.blue,color.alpha)]
    end
    def set_font(font,state)
      font.name=state[0];font.size=state[1];font.bold=state[2]
      font.italic=state[3];font.color=state[4]
    end
    def before_draw(bitmap,args)
      rect=rect_args(args)
      invalidate(bitmap,rect)
      return [args,nil] unless owner(bitmap)
      index=args[0].respond_to?(:width) ? 1 : 4
      raw=args[index]
      return [args,nil] unless raw.is_a?(String) && raw.size>0 && !IATraductoraXP.identity?(raw)
      translated=value(raw)
      if translated!=raw
        copy=args.dup;copy[index]=translated;@applied+=1
        return [copy,nil]
      end
      return [args,nil] unless rect && rect.all? { |n| n.is_a?(Integer) }
      x,y,w,h=rect
      # Width zero and clipped custom text still get ready/dictionary
      # translations, but cannot safely schedule a region replay.
      return [args,nil] unless x>=0 && y>=0 && w>0 && h>0 &&
        x+w<=bitmap.width && y+h<=bitmap.height && w*h<=160000
      key=[term_mode(raw),raw.dup]
      entry=@plans[key]
      if !entry
        return [args,nil] if @plans.size>=64
        p=IATraductoraXP.plan(raw,key[0])
        return [args,nil] unless p && !p[:entries].empty?
        entry={:plan=>p,:raw=>raw.dup,:done=>false}
        @plans[key]=entry
      end
      return [args,nil] if entry[:done] || @jobs.size>=24
      total=@jobs.inject(0) { |n,j| n+j[:rect][2]*j[:rect][3] }
      return [args,nil] if total+w*h>1200000
      snapshot=nil
      begin
        snapshot=Bitmap.new(w,h)
        snapshot.blt(0,0,bitmap,Rect.new(x,y,w,h))
        job={:bitmap=>bitmap,:rect=>rect.dup,:raw=>raw.dup,
          :align=>args[index+1]||0,:font=>font_state(bitmap.font),
          :snapshot=>snapshot,:entry=>entry}
        @jobs.push(job)
        [args,job]
      rescue StandardError
        snapshot.dispose if live?(snapshot)
        [args,nil]
      end
    rescue StandardError
      [args,nil]
    end
    def apply(job,translated)
      bitmap=job[:bitmap]
      return unless owner(bitmap) && translated!=job[:raw]
      x,y,w,h=job[:rect]
      return unless x+w<=bitmap.width && y+h<=bitmap.height
      saved=font_state(bitmap.font)
      @painting=true
      begin
        # RGSS1 has fill_rect, NOT RGSS2 clear_rect. Restore only the
        # untouched captured region before calling the native renderer.
        bitmap.fill_rect(x,y,w,h,Color.new(0,0,0,0))
        bitmap.blt(x,y,job[:snapshot],Rect.new(0,0,w,h))
        set_font(bitmap.font,job[:font])
        bitmap.ia_xp_bitmap_draw_text(x,y,w,h,translated,job[:align])
        @applied+=1
      rescue StandardError
        # If the replacement text is rejected by the native renderer,
        # restore the original draw rather than leaving a blank region.
        bitmap.fill_rect(x,y,w,h,Color.new(0,0,0,0))
        bitmap.blt(x,y,job[:snapshot],Rect.new(0,0,w,h))
        set_font(bitmap.font,job[:font])
        bitmap.ia_xp_bitmap_draw_text(x,y,w,h,job[:raw],job[:align])
      ensure
        set_font(bitmap.font,saved)
        @painting=false
      end
    rescue StandardError
      @painting=false
    end
    def tick
      now=Time.now.to_f
      return if now<@next_tick
      @next_tick=now+0.04
      prune
      budget=8
      @plans.keys.each do |key|
        break if budget<=0
        entry=@plans[key]
        next if entry[:done]
        budget-=1
        if IATraductoraXP.advance(entry[:plan])
          entry[:done]=true
          entry[:value]=IATraductoraXP.render(entry[:plan],entry[:raw])
        end
      end
      @jobs.dup.each do |job|
        entry=job[:entry]
        if entry[:done]
          apply(job,entry[:value]) if entry[:plan][:entries].empty?
          drop(job)
        end
      end
      @plans.delete_if { |key,entry| entry[:done] }
    rescue StandardError
      nil
    end
    def key_f10
      return false unless defined?(Win32API)
      @foreground||=Win32API.new('user32','GetForegroundWindow','','l')
      @window_pid||=Win32API.new('user32','GetWindowThreadProcessId','lp','l')
      @key||=Win32API.new('user32','GetAsyncKeyState','i','i')
      pid=[0].pack('L')
      @window_pid.call(@foreground.call,pid)
      return false unless pid.unpack('L')[0]==Process.pid
      (@key.call(0x79)&0x8000)!=0
    rescue StandardError
      false
    end
    def badge
      return unless defined?(Sprite) && defined?(Bitmap) && defined?(Color)
      down=key_f10
      @details=!@details if down && !@key_down
      changed=down && !@key_down
      @key_down=down
      now=Time.now.to_f
      return if !changed && now<@next_badge
      @next_badge=now+0.5
      active=IATraductoraXP.session_active?
      label=active ? 'IA Traductora - Activa' : 'IA Traductora - Sin conexion'
      label='IA | UI: '+@applied.to_s+' | F10' if @details
      if !live?(@badge)
        @badge=Sprite.new
        @badge.bitmap=Bitmap.new(228,24)
        @badge.z=10000
        @badge.x=(Graphics.respond_to?(:width) ? Graphics.width : 640)-232
        @badge.y=4
        @badge_key=nil
      end
      return if @badge_key==label
      @badge_key=label
      b=@badge.bitmap
      b.clear
      b.fill_rect(0,0,228,24,Color.new(12,25,45,216))
      b.font.name='Arial'
      b.font.size=14
      b.font.color=Color.new(255,255,255,255)
      b.draw_text(4,0,220,24,label,1)
    rescue StandardError
      nil
    end
  end
end

if defined?(Window_Base)
  class Window_Base
    if method_defined?(:contents=)
      alias_method :ia_xp_contents_assign, :contents=
      def contents=(bitmap)
        old=self.contents
        IATraductoraXPUI.invalidate(old) if old
        result=ia_xp_contents_assign(bitmap)
        IATraductoraXPUI.register(self,bitmap)
        result
      end
    end
    if method_defined?(:draw_actor_name)
      alias_method :ia_xp_draw_actor_name, :draw_actor_name
      def draw_actor_name(*args,&block)
        IATraductoraXPUI.without_translation { ia_xp_draw_actor_name(*args,&block) }
      end
    end
  end
end
if defined?(Window_Help) && Window_Help.method_defined?(:set_enemy)
  class Window_Help
    alias_method :ia_xp_help_enemy, :set_enemy
    def set_enemy(*args,&block)
      IATraductoraXPUI.without_translation { ia_xp_help_enemy(*args,&block) }
    end
  end
end
if defined?(Bitmap) && Bitmap.method_defined?(:draw_text)
  class Bitmap
    alias_method :ia_xp_bitmap_draw_text, :draw_text
    def draw_text(*args,&block)
      converted,job=IATraductoraXPUI.before_draw(self,args)
      ok=false
      begin
        result=ia_xp_bitmap_draw_text(*converted,&block)
        ok=true
        result
      ensure
        IATraductoraXPUI.drop(job) if job && !ok
      end
    end
    if method_defined?(:text_size)
      alias_method :ia_xp_bitmap_text_size, :text_size
      def text_size(value)
        value=IATraductoraXPUI.value(value) if IATraductoraXPUI.owner(self)
        ia_xp_bitmap_text_size(value)
      end
    end
    # Ruby 1.8-compatible aliases, explicit methods rather than a
    # closure-dependent define_method loop with shared loop variables.
    alias_method :ia_xp_bitmap_clear, :clear
    def clear(*args)
      IATraductoraXPUI.mutation(self,:clear,args)
      ia_xp_bitmap_clear(*args)
    end
    alias_method :ia_xp_bitmap_fill, :fill_rect
    def fill_rect(*args)
      IATraductoraXPUI.mutation(self,:fill_rect,args)
      ia_xp_bitmap_fill(*args)
    end
    alias_method :ia_xp_bitmap_blt, :blt
    def blt(*args)
      IATraductoraXPUI.mutation(self,:blt,args)
      ia_xp_bitmap_blt(*args)
    end
    if method_defined?(:stretch_blt)
      alias_method :ia_xp_bitmap_stretch, :stretch_blt
      def stretch_blt(*args)
        IATraductoraXPUI.mutation(self,:stretch_blt,args)
        ia_xp_bitmap_stretch(*args)
      end
    end
    if method_defined?(:set_pixel)
      alias_method :ia_xp_bitmap_pixel, :set_pixel
      def set_pixel(*args)
        IATraductoraXPUI.mutation(self,:set_pixel,args)
        ia_xp_bitmap_pixel(*args)
      end
    end
    if method_defined?(:hue_change)
      alias_method :ia_xp_bitmap_hue, :hue_change
      def hue_change(*args)
        IATraductoraXPUI.mutation(self,:hue_change,args)
        ia_xp_bitmap_hue(*args)
      end
    end
    alias_method :ia_xp_bitmap_dispose, :dispose
    def dispose(*args)
      IATraductoraXPUI.invalidate(self)
      ia_xp_bitmap_dispose(*args)
    end
  end
end
if defined?(Graphics) && Graphics.respond_to?(:update)
  class << Graphics
    alias_method :ia_xp_graphics_update, :update
    def update(*args,&block)
      result=ia_xp_graphics_update(*args,&block)
      IATraductoraXPUI.tick
      IATraductoraXPUI.badge
      result
    end
  end
end

# The installed adapter starts its verified helper on the native game process.
IATraductoraXP.start_native
