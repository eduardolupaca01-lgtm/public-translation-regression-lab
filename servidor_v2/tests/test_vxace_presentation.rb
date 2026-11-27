# encoding: UTF-8
# Independently authored native-surface contract. No commercial game assets.
require 'tmpdir'
require 'fileutils'

Rect = Struct.new(:x,:y,:width,:height)
Color = Struct.new(:red,:green,:blue,:alpha)
Font = Struct.new(:size,:color)
class Bitmap
  attr_accessor :font
  attr_reader :width,:height,:draws
  def initialize(w,h); @width=w; @height=h; @font=Font.new(20,nil); @draws=[]; @disposed=false; end
  def disposed?; @disposed; end
  def dispose; @disposed=true; end
  def clear; @draws.clear; end
  def fill_rect(*args); end
  def text_size(text); Rect.new(0,0,text.each_char.to_a.length * (@font.size/2),@font.size); end
  def draw_text(*args)
    rect=args[0].is_a?(Rect) ? args[0] : Rect.new(*args[0,4])
    text=args[0].is_a?(Rect) ? args[1] : args[4]
    @draws << [rect,text,@font.size]
  end
end
class Sprite
  attr_accessor :bitmap,:x,:y,:z,:visible
  def disposed?; false; end
end
module Graphics
  def self.width; 544; end
  def self.height; 416; end
  def self.update; :frame; end
end
class Window_Base
  attr_accessor :contents,:visible,:openness
  def initialize(w=120,h=48)
    @w=w; @h=h; @visible=true; @openness=255; create_contents
  end
  def create_contents; self.contents=Bitmap.new(@w,@h); end
  def contents_width; @w; end
  def disposed?; false; end
  def draw_text(*args); contents.draw_text(*args); end
  def draw_text_ex(x,y,text); @rich=text; contents.draw_text(x,y,@w-x,24,text); end
  def rich; @rich; end
end
class Game_Message
  attr_reader :texts,:choices
  def initialize; @texts=[]; @choices=[]; end
end
class Window_Message < Window_Base
  attr_reader :pages,:glyphs,:pauses,:codes
  def process_all_text
    @glyphs=[]; @codes=[]; @pages=1; @pauses=0
    text=$game_message.texts.join("\n").gsub(/\\C\[/,"\eC[")
    pos={:x=>20,:new_x=>20,:y=>0,:height=>20}
    process_character(text.slice!(0,1),text,pos) until text.empty?
  end
  def input_choice; end
  def process_character(c,text,pos)
    if c=="\e"
      @codes << text.slice!(/\AC\[\d+\]/)
    elsif c=="\n"
      process_new_line(text,pos)
    else
      width=contents.text_size(c).width
      @glyphs << [c,pos[:x],pos[:y],@pages,width]
      pos[:x]+=width
    end
  end
  def process_new_line(text,pos)
    pos[:x]=pos[:new_x]
    pos[:y]+=pos[:height]
    if pos[:y]+pos[:height]>contents.height && !text.empty?
      @pauses+=1; @pages+=1; pos[:y]=0
    end
  end
end
class Window_Menu < Window_Base
  attr_reader :refreshes,:index,:symbols
  def initialize
    @refreshes=0; @index=1; @symbols=[:magic,:gear,:custom]; super(150,96)
  end
  def refresh
    @refreshes+=1
    contents.clear
    contents.draw_text(Rect.new(0,0,140,24),'Magic/Item')
    draw_text(0,24,140,24,'Gear')
    draw_text(0,48,140,24,'Open the gate.')
    draw_text(0,72,140,24,'Raptor')
  end
end
class Window_Help < Window_Base; end
class Window_NameEdit < Window_Base; end
Actor=Struct.new(:name,:nickname)
Party=Struct.new(:members)
$game_party=Party.new([Actor.new('Raptor','Hero')])
$data_actors=[nil,Actor.new('Raptor','Hero')]
$game_message=Game_Message.new

def assert(value,label); raise label unless value; end
PLUGIN=File.expand_path('../vxace/IATraductoraVXACE.rb',File.dirname(__FILE__))
SIDECAR=File.join('IA Traductora','.local','Rpg')
TOKEN='b'*64
LONG='Este diálogo es bastante largo y necesita saltos de línea completos.'
SOURCE='This dialogue is long.'
def respond_to_requests
  Dir.glob(File.join(SIDECAR,'vxace-ipc',TOKEN,'*.req')).each do |file|
    fields=File.binread(file).split("\n")
    assert(fields[0]=='IA-VXACE-REQUEST-1' && fields[1]==TOKEN,'authentication')
    id=File.basename(file,'.req')
    values=fields[3..-1].map do |hex|
      s=[hex].pack('H*').force_encoding('UTF-8')
      value={SOURCE=>LONG,'Open the gate.'=>'Abre la puerta.','A long help description.'=>'Una descripción de ayuda con varias palabras.'}[s]
      value ? value.unpack('H*')[0] : '-'
    end
    File.delete(file)
    out=file.sub(/\.req$/,'.res')
    File.binwrite(out+'.tmp',(['IA-VXACE-RESPONSE-1',TOKEN,id]+values).join("\n")+"\n")
    File.rename(out+'.tmp',out)
  end
end
def tick
  Graphics.update
  respond_to_requests
  sleep 0.05
end
Dir.mktmpdir('vxace presentation ') do |root|
  Dir.chdir(root) do
    File.binwrite('Game.exe','fixture')
    FileUtils.mkdir_p(File.join(SIDECAR,'vxace-ipc',TOKEN))
    File.binwrite(File.join(SIDECAR,'vxace-session.txt'),"IA-VXACE-SESSION-1\n#{TOKEN}\n1234\n#{Process.pid}\n")
    load PLUGIN
    original=['\C[2]'+SOURCE+'\C[0]']
    $game_message.texts.replace(original)
    message=Window_Message.new(120,40)
    fiber=Fiber.new { message.process_all_text }
    160.times do
      break unless fiber.alive?
      fiber.resume
      tick if fiber.alive?
    end
    assert(!fiber.alive?,'message fiber did not finish')
    assert(message.pages>1 && message.pauses==message.pages-1,'native page transition missing')
    assert(message.glyphs.all? { |c,x,y,p,w| x+w<=message.contents.width-3 && y+20<=message.contents.height },'dialogue exceeds native rectangle')
    assert(message.glyphs.map { |g| g[0] }.join.gsub(/\s/,'')==LONG.gsub(/\s/,''),'dialogue lost characters')
    assert(message.codes==['C[2]','C[0]'],'control code altered')
    assert($game_message.texts==original,'original event data modified')
    wrapped=IATraductoraVXACE.wrap_raw(message,'\C[2]'+LONG+'\C[0]',90)
    assert(wrapped.include?("\n") && wrapped.gsub(/\s/,'')==('\C[2]'+LONG+'\C[0]').gsub(/\s/,''),'scroll wrapping lost text/control')
    assert(wrapped.lines.all? { |l| message.contents.text_size(l.gsub(/\\C\[\d+\]/,'').strip).width<=90 },'scroll line too wide')
    puts 'IA_VXACE_PIXEL_WRAP_AND_NATIVE_PAGINATION_PASS'

    menu=Window_Menu.new
    menu.refresh
    assert(menu.contents.draws[0][1]=='Magia/Objetos','direct Bitmap menu not translated')
    assert(menu.contents.draws[1][1]=='Equipo','standard menu not translated')
    assert(menu.contents.draws[3][1]=='Raptor','actor name altered')
    assert(menu.contents.draws[2][1]=='Open the gate.','unknown label was not preserved while waiting')
    100.times do
      tick
      break if menu.contents.draws.any? { |d| d[1]=='Abre la puerta.' }
    end
    assert(menu.contents.draws.any? { |d| d[1]=='Abre la puerta.' },'async native refresh not translated')
    assert(menu.index==1 && menu.symbols==[:magic,:gear,:custom],'selection or command symbol altered')
    assert(menu.contents.font.size==20,'font size leaked into later draws')
    count=IATraductoraVXACE.requests
    menu.refresh
    assert(IATraductoraVXACE.requests==count,'menu cached text requested twice')
    input=Window_NameEdit.new
    input.draw_text(0,0,100,24,'Gear')
    assert(input.contents.draws.last[1]=='Gear','editable field translated')
    help=Window_Help.new(120,120)
    100.times do
      help.draw_text_ex(0,0,'A long help description.')
      tick
      break if help.rich!='A long help description.'
    end
    assert(help.rich.include?("\n") && help.rich.include?('descripción'),'rich help text not wrapped')
    puts 'IA_VXACE_NATIVE_MENU_BITMAP_HELP_AND_NAME_GUARD_PASS'

    hud=IATraductoraVXACE.instance_variable_get(:@hud_sprite)
    assert(hud && hud.visible && hud.x+hud.bitmap.width<=Graphics.width,'persistent badge missing')
    assert(hud.bitmap.draws.any? { |d| d[1].include?('IA Traductora') && d[1].include?('F10') },'badge label missing')
    class << IATraductoraVXACE
      alias_method :qa_original_f10, :f10?
      def f10?; result=@qa_f10; @qa_f10=false; result; end
    end
    IATraductoraVXACE.instance_variable_set(:@qa_f10,true)
    tick
    assert(hud.bitmap.height>26 && hud.bitmap.draws.any? { |d| d[1].include?('Solicitudes') },'F10 diagnostics missing')
    IATraductoraVXACE.instance_variable_set(:@qa_f10,true)
    tick
    assert(hud.bitmap.height==26 && hud.visible,'F10 did not return to compact badge')
    puts 'IA_VXACE_PERSISTENT_BADGE_F10_PASS'
  end
end
