# No desktop Ruby emulation: this script is loaded by the selected Game.exe.
def xp_probe_report(code)
  File.open('xp-native-result.tmp','wb') { |f| f.write(code+"\n") }
  File.rename('xp-native-result.tmp','xp-native-result.txt')
end
def xp_probe_frame
  Graphics.update
  Input.update
end
phase='RUNTIME'
window=nil
begin
  raise 'wrong runtime' unless RUBY_VERSION =~ /\A1\.8\./
  raise 'missing API' unless defined?(Win32API) && defined?(Graphics) && defined?(Bitmap) && defined?(Window)
  pid=Win32API.new('kernel32','GetCurrentProcessId','','l').call
  raise 'PID mismatch' unless pid==Process.pid
  phase='SESSION'
  bridge=IATraductoraXP::FileBridge.new
  deadline=Time.now.to_f+100
  until bridge.session
    raise 'session timeout' if Time.now.to_f>=deadline
    xp_probe_frame
  end
  phase='TRANSLATE'
  japanese=[0x6a4b,0x3092,0x6e21,0x3063,0x3066,0x304f,0x3060,0x3055,0x3044,0x3002].pack('U*')
  raw="\\C[2]Please open the wooden gate.\\C[0]\n"+japanese+"\nWait here.\n"
  $game_temp=Game_Temp.new
  $game_temp.message_text=raw.dup
  $game_temp.choice_start=2
  $game_temp.choice_max=1
  chosen=[]
  callback=proc { |i| chosen.push(i) }
  $game_temp.choice_proc=callback
  window=Window_Message.new
  deadline=Time.now.to_f+12
  while window.paints==0 && Time.now.to_f<deadline
    window.update
    xp_probe_frame
  end
  shown=window.painted
  raise 'missing translation' unless window.paints==1 && shown && shown!=raw
  lines=shown.split("\n")
  raise 'line mismatch' unless lines.length==3
  raise 'English' unless lines[0] =~ /puerta|port.n|verja/i && lines[0] =~ /madera/i
  raise 'Japanese' unless lines[1] =~ /puente/i && !IATraductoraXP.japanese?(lines[1])
  raise 'choice' unless lines[2] =~ /esper|aguard/i
  phase='PAINT'
  raise 'native bitmap' unless window.pixels
  raise 'controls' unless lines[0].index('\\C[2]')==0 && lines[0][-5,5]=='\\C[0]'
  raise 'original text changed' unless $game_temp.message_text==raw
  raise 'choice state changed' unless $game_temp.choice_proc.equal?(callback) && $game_temp.choice_start==2 && $game_temp.choice_max==1
  $game_temp.choice_proc.call(0)
  raise 'choice callback failed' unless chosen==[0]
  xp_probe_frame
  xp_probe_report('IA_RPGXP_NATIVE_PAINT_PASS')
  # Allow the external runner to verify the real worker's counters while
  # it is alive. No token, game content or path is written to the report.
  deadline=Time.now.to_f+20
  until File.file?('xp-native-ack.txt')
    raise 'ack timeout' if Time.now.to_f>=deadline
    xp_probe_frame
  end
rescue StandardError, ScriptError
  xp_probe_report('IA_RPGXP_NATIVE_'+phase+'_FAIL') unless File.file?('xp-native-result.txt')
  exit
ensure
  if window && !window.disposed?
    bitmap=window.contents
    window.dispose
    bitmap.dispose if bitmap && !bitmap.disposed?
  end
end
