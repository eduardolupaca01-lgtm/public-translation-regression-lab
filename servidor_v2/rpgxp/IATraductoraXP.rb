# IA_TRADUCTORA_RPGXP_RGSS1_OWNER_V1
# RGSS1 / Ruby 1.8. A presentation adapter, not an installer.
# No Fiber, String#encode, encoding metadata, native overlay or eval.
# A separately verified transport supplies poll(lang, text). Until one
# is attached, native messages continue unchanged.
module IATraductoraXP
  BUILD = 'RPGXP-RGSS1-R43-LAB-2'
  MAX_WAIT = 8.0
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
    def source(value)
      return nil if !codepoints(value) || value =~ /[\x00-\x1f\\<>]/
      return 'ja' if japanese?(value)
      return nil if value =~ /[\x80-\xff]/n
      return nil if value =~ /\A(?:[A-Za-z0-9_]+\.[A-Za-z0-9]+|[A-Z0-9_]{2,})\z/
      words = value.scan(/[A-Za-z]+/)
      return 'en' if words.length >= 2 && value =~ /\b(?:the|you|your|please|here|there|is|are|open|close|thank|where|what|how|have|will|can|go|wait|my|we|it|this|that|with|from|and|to|of|for)\b/i
      return 'en' if value =~ /\A(?:yes|no|cancel|continue|attack|defend|save|load|exit|wait|help|hello|thanks)[.!?]?\z/i && value.downcase!='no'
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
    def plan(raw)
      return nil unless @transport && raw.is_a?(String) && raw.length<=MAX_BYTES && codepoints(raw)
      pieces=raw.split(CONTROL,-1)
      # Unknown control syntax is not prose. Preserve this whole message.
      pieces.each_with_index do |piece,i|
        return nil if i%2==0 && piece =~ /[\\\x00-\x1f<>]/
      end
      entries=[]
      pieces.each_with_index do |piece,i|
        next if i%2==1
        lead=piece[/\A[ \t]*/] || ''
        tail=piece[/[ \t]*\z/] || ''
        next if lead.length+tail.length>=piece.length
        body=piece[lead.length,piece.length-lead.length-tail.length]
        lang=source(body)
        next unless lang
        key=[lang,body]
        if @cache.has_key?(key)
          pieces[i]=lead+@cache[key]+tail
        else
          entries.push([i,key,lead,tail])
        end
      end
      {:pieces=>pieces,:entries=>entries,:until=>Time.now.to_f+MAX_WAIT}
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
    def render(p,raw)
      return raw unless p
      # Never expose a half-translated choice set / dialogue. Fail open
      # if a required piece timed out or was rejected.
      p[:entries].empty? ? p[:pieces].join : raw
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
      shown=IATraductoraXP.render(pending[2],raw)
      return ia_xp_original_refresh(*args,&block) if shown==raw
      # The stock XP refresh destructively consumes its input String.
      # Give it a temporary copy; restore only if it still owns that copy.
      projected=shown.dup
      $game_temp.message_text=projected
      begin
        ia_xp_original_refresh(*args,&block)
      ensure
        $game_temp.message_text=raw if $game_temp.message_text.equal?(projected)
      end
    end
  end
end

# The installed adapter starts its verified helper on the native game process.
IATraductoraXP.start_native
