# encoding: UTF-8
# Synthetic XP-native window plus the actual file bridge; no original assets.
class Game_Temp
  attr_accessor :message_text,:choice_proc,:choice_start,:choice_max,:num_input_variable_id
  def initialize
    @num_input_variable_id=0
  end
end
class Window_Message
  attr_reader :painted,:paints
  def initialize
    @contents_showing=false
    @fade_in=@fade_out=false
    @paints=0
  end
  def update
    if !@contents_showing && $game_temp.message_text
      refresh
      @contents_showing=true
    end
  end
  def refresh
    @paints+=1
    @painted=$game_temp.message_text.dup
    $game_temp.message_text.replace('')
  end
end
require File.expand_path('../rpgxp/IATraductoraXP.rb',File.dirname(__FILE__))
IATraductoraXP.attach(IATraductoraXP::FileBridge.new)
raw="\\C[2]Please open the door.\\C[0]\nおはようございます。\nWait here.\n"
$game_temp=Game_Temp.new
$game_temp.message_text=raw.dup
$game_temp.choice_start=2
$game_temp.choice_max=1
choice=proc { |i| i }
$game_temp.choice_proc=choice
window=Window_Message.new
deadline=Time.now.to_f+7.5
while window.paints==0 && Time.now.to_f<deadline
  window.update
  sleep 0.02 if window.paints==0
end
raise 'IA_RPGXP_BRIDGE_NATIVE_PAINT' unless window.paints==1
raise 'IA_RPGXP_BRIDGE_TRANSLATION' unless window.painted=="\\C[2]Abre la puerta.\\C[0]\nBuenos días.\nEspera aquí.\n"
raise 'IA_RPGXP_BRIDGE_SOURCE_CHANGED' unless $game_temp.message_text==raw
raise 'IA_RPGXP_BRIDGE_CHOICES_CHANGED' unless $game_temp.choice_proc.equal?(choice) && $game_temp.choice_start==2 && $game_temp.choice_max==1
puts 'IA_RPGXP_NATIVE_IPC_FIRST_VIEW_PASS'
