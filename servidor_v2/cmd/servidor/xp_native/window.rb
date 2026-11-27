# Original laboratory code, deliberately compatible with Ruby 1.8.
class Game_Temp
  attr_accessor :message_text,:choice_proc,:choice_start,:choice_max,:num_input_variable_id
  def initialize
    @num_input_variable_id=0
  end
end

# Synthetic stock-style message contract, with REAL RGSS Window and Bitmap.
# No game scripts, maps, assets or save files are loaded.
class Window_Message < Window
  attr_reader :painted,:paints,:pixels
  def initialize
    super()
    self.x=24
    self.y=280
    self.width=592
    self.height=128
    self.opacity=0
    self.contents=Bitmap.new(560,96)
    @contents_showing=false
    @fade_in=@fade_out=false
    @paints=0
    @pixels=false
  end
  def update
    super
    if !@contents_showing && $game_temp.message_text
      refresh
      @contents_showing=true
    end
  end
  def refresh
    @paints+=1
    @painted=$game_temp.message_text.dup
    self.contents.clear
    @painted.split("\n").each_with_index do |line,i|
      text=line.gsub(/\\[Cc]\[[0-9]+\]/,'')
      raise 'native text width' unless self.contents.text_size(text).width>0
      self.contents.draw_text(0,i*32,560,32,text)
    end
    # Check each line actually left nontransparent pixels in the RGSS bitmap.
    @pixels=true
    3.times do |row|
      found=false
      (row*32...(row+1)*32).each do |y|
        break if found
        (0...560).each do |x|
          if self.contents.get_pixel(x,y).alpha>0
            found=true
            break
          end
        end
      end
      @pixels=false unless found
    end
    $game_temp.message_text.replace('')
  end
end
