# IA_TRADUCTORA_RPGXP_RGSS1_OWNER_V1
# RGSS1 / Ruby 1.8. A presentation adapter, not an installer.
# No Fiber, String#encode, encoding metadata, native overlay or eval.
# A separately verified transport supplies poll(lang, text). Until one
# is attached, native messages continue unchanged.
module IATraductoraXP
  BUILD = 'RPGXP-RGSS1-R43-LAB-1'
  MAX_WAIT = 8.0
  MAX_CACHE = 4096
  MAX_BYTES = 7200
  CONTROL = /(\\\\|\\[vncVNC]\[[0-9]+\]|\\[gG](?![A-Za-z])|\r\n|\r|\n|%[0-9]+|%[sd]|\{[A-Za-z_][A-Za-z0-9_]*\})/
  @cache = {}
  @order = []
  @transport = nil
  class << self
    def attach(transport)
      @transport = transport
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
      value.scan(/[0-9]+/).map { |n| n.sub(/\A0+(?=[0-9])/,'') }.sort
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
      return nil if pieces.each_with_index.any? { |p,i| i%2==0 && p =~ /[\\\x00-\x1f<>]/ }
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
