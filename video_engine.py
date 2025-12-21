import os
import json
import logging
import re
import random
import shutil
import time
import textwrap
import copy
from typing import Optional, List, Dict, Any, Tuple, Callable

from dotenv import load_dotenv
import google.generativeai as genai
from google.cloud import texttospeech
from mutagen.mp3 import MP3
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance
from bs4 import BeautifulSoup
import ffmpeg
from moviepy import ImageClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip
from moviepy.audio.fx import AudioLoop, AudioFadeOut

# Load environment variables
load_dotenv()

# Logger Setup
def setup_logging(debug_mode: bool = False):
    level = logging.DEBUG if debug_mode else logging.INFO
    
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Check if handlers already exist to avoid duplicates
    if not logger.handlers:
        # File Handler
        try:
            file_handler = logging.FileHandler('app.log')
            file_handler.setLevel(level)
            file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Failed to setup file handler: {e}")
        
        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    else:
        # Update level if it changes
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)

logger = logging.getLogger(__name__)

# Load configuration
def load_config(config_path: str = 'config.json') -> Dict[str, Any]:
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"{config_path} not found.")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding {config_path}: {e}")
        return {}

def format_time(seconds: float) -> str:
    """
    Helper to convert seconds into readable string (e.g., "1m 30s" or "45s").
    """
    m, s = divmod(int(seconds), 60)
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"

def resolve_character_key(name: str, config: Dict[str, Any]) -> Optional[str]:
    """
    Robustly resolves a character name from the script to a key in config.json.
    """
    if not name or name == "Narrator":
        return None

    valid_keys = config.get('characters', {}).keys()
    
    # Strategy 1: Exact Match
    if name in valid_keys:
        return name
        
    # Strategy 2: Case-Insensitive
    for key in valid_keys:
        if key.lower() == name.lower():
            return key
            
    # Strategy 3: Partial Match (Name starts with Key)
    for key in valid_keys:
        if name.lower().startswith(key.lower()):
            return key
            
    # Strategy 4: Reverse Partial (Key starts with Name)
    for key in valid_keys:
        if key.lower().startswith(name.lower()):
            return key
            
    return None

def get_active_roster(parsed_script: List[Dict[str, Any]], config: Dict[str, Any]) -> List[str]:
    """
    Extracts unique char names (excluding Narrator) to determine who is on stage.
    """
    roster = set()
    
    for line in parsed_script:
        speaker = line.get('speaker')
        if speaker and speaker != "Narrator":
            resolved_key = resolve_character_key(speaker, config)
            if resolved_key:
                roster.add(resolved_key)
    
    return list(roster)

def extract_vocabulary(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """
    Helper: Extracts vocabulary cards from HTML
    """
    vocab_list = []
    cards = soup.find_all('div', class_='vocab-card')
    
    for card in cards:
        # 1. Word
        word_elem = card.find('h4', class_='word')
        word = word_elem.get_text(strip=True) if word_elem else ""
        
        # 2. Translation
        trans_elem = card.find('div', class_='vocab-card-translate')
        translation = ""
        if trans_elem:
            raw_trans = trans_elem.get_text(separator=' ', strip=True)
            translation = re.sub(r'^Translate:?\s*', '', raw_trans, flags=re.IGNORECASE)
            translation = re.sub(r'\s+', ' ', translation).strip()
            
        # 3. Example
        ex_elem = card.find('div', class_='vocab-card-example')
        example = ""
        if ex_elem:
            raw_ex = ex_elem.get_text(separator=' ', strip=True)
            example = re.sub(r'^Example:?\s*', '', raw_ex, flags=re.IGNORECASE)
            example = re.sub(r'\s+', ' ', example).strip()
            
        if word:
            vocab_list.append({
                "word": word,
                "translation": translation,
                "example": example
            })
            
    return vocab_list

def clean_html_content(raw_html: str) -> Tuple[str, List[Dict[str, str]], str]:
    """
    Step 0: Clean HTML Content
    Extracts English dialogue from specific lesson structures.
    """
    soup = BeautifulSoup(raw_html, 'html.parser')
    
    # Step 0: Extract Vocabulary
    vocab_list = extract_vocabulary(soup)
    
    # Step 0.5: Extract Lesson Title
    lesson_title_tag = soup.find('h2')
    lesson_title = lesson_title_tag.get_text(strip=True) if lesson_title_tag else "Untitled Lesson"

    # Step A: Locate Content
    section = soup.find('section', class_='vocabulary-story')
    if not section:
        section = soup.find('section', class_='dialogue')
    
    target_content = section if section else (soup.body if soup.body else soup)

    if hasattr(target_content, 'decode_contents'):
        text = target_content.decode_contents()
    else:
        text = str(target_content)

    # Step B: Cleaning
    # 1. Newlines: <br> -> \n
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    
    # 2. Remove Italian Translations: [tooltip]...[/tooltip]
    text = re.sub(r'\[tooltip\].*?\[/tooltip\]', ' ', text, flags=re.DOTALL)
    
    # 3. Remove Custom Tags: [esempio] and [/esempio]
    text = re.sub(r'\[/?esempio\]', ' ', text)
    
    # 4. Strip HTML tags
    temp_soup = BeautifulSoup(text, 'html.parser')
    final_text = temp_soup.get_text(separator=' ')
    
    # Clean up excessive whitespace
    final_text = re.sub(r'\s+', ' ', final_text).strip()
    
    return final_text, vocab_list, lesson_title

def generate_dual_scripts(raw_text: str, config: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Step 1 & 2: Dual Brain Logic
    Generates TWO scripts:
    1. Social Script (Fast-paced, dialogue only)
    2. Web Script (Verbatim, full structure)
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not found in environment variables.")
        return [], []

    social_script = []
    web_script = []

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(config.get('gemini_model', 'gemini-pro'))

        # --- CALL B: WEB SCRIPT ---
        logger.info("Generating Web Script (Call B)...")
        web_prompt = """
        You are an expert script parser. Your task is to transcribe the ENTIRE story verbatim from the raw text.
    
        RULES:
        1. IDENTIFY SPEAKERS: Identify every line's speaker (Herbert, Margot, Brian, Laura, Molly).
        2. NARRATOR: Explicitly tag descriptive text as speaker: "Narrator".
        3. CHARACTERS: Tag dialogue with the character's name.
        4. VERBATIM: Keep the text EXACTLY as it is in the input. Do not summarize. Retrieve every sentence.
        
        OUTPUT: A JSON object with a single key web_script: [{"speaker": "Narrator", "text": "Herbert looks at the map."}, {"speaker": "Herbert", "text": "I am lost."}]
        """
        
        full_web_prompt = f"{web_prompt}\n\nRAW TEXT:\n{raw_text}"
        response_web = model.generate_content(full_web_prompt)
        text_web = response_web.text
        
        # Cleanup
        if text_web.startswith("```json"): text_web = text_web[7:]
        if text_web.startswith("```"): text_web = text_web[3:]
        if text_web.endswith("```"): text_web = text_web[:-3]
        
        try:
             web_json = json.loads(text_web)
             web_script = web_json.get("web_script", [])
        except json.JSONDecodeError as e:
            logger.error(f"JSON Error (Web): {e}")
            
        # Social Script Strategy: Truncated Version of Web Script (First 6 lines)
        social_script = web_script[:6]
            
        return social_script, web_script

    except Exception as e:
        logger.error(f"Error generating dual scripts: {e}", exc_info=True)
        return [], []

def generate_single_audio(text: str, speaker: str, index: int, config: Dict[str, Any], output_dir: str = "output") -> Tuple[Optional[str], float]:
    """
    Step 2a: Generate Audio
    - Uses Google Cloud TTS
    - Returns filename and duration
    """
    os.makedirs(output_dir, exist_ok=True)

    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        # Log warning if needed, but assuming env is set
        pass

    try:
        client = texttospeech.TextToSpeechClient()
    except Exception as e:
        logger.error(f"Failed to initialize TTS client: {e}", exc_info=True)
        return None, 0.0

    # Determine Voice Params
    voice_params = None
    if speaker == "Narrator":
        voice_params = config.get('narrator', {}).get('voice_params')
    else:
        resolved_key = resolve_character_key(speaker, config)
        if resolved_key:
            char_config = config.get('characters', {}).get(resolved_key)
            if char_config:
                voice_params = char_config.get('voice_params')

    if not voice_params:
        voice_params = config.get('narrator', {}).get('voice_params') 
    
    if not voice_params:
         logger.critical(f"No voice params found for {speaker} and no default narrator config.")
         return None, 0.0

    # Prepare Request
    synthesis_input = texttospeech.SynthesisInput(text=text)
    
    gender_map = {
        "MALE": texttospeech.SsmlVoiceGender.MALE,
        "FEMALE": texttospeech.SsmlVoiceGender.FEMALE,
        "NEUTRAL": texttospeech.SsmlVoiceGender.NEUTRAL
    }
    gender_str = voice_params.get("ssml_gender", "MALE")
    gender_enum = gender_map.get(gender_str, texttospeech.SsmlVoiceGender.MALE)

    voice = texttospeech.VoiceSelectionParams(
        language_code=voice_params.get("language_code", "en-US"),
        name=voice_params.get("name"),
        ssml_gender=gender_enum
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )

    try:
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
    except Exception as e:
        logger.error(f"TTS API Error for {speaker}: {e}", exc_info=True)
        return None, 0.0

    filename = f"audio_{index}.mp3"
    filepath = os.path.join(output_dir, filename)
    filepath = os.path.abspath(filepath) 

    with open(filepath, "wb") as out:
        out.write(response.audio_content)
        
    try:
        audio = MP3(filepath)
        duration = audio.info.length
    except Exception as e:
        logger.warning(f"Could not determine duration for {filepath}: {e}")
        duration = 0.0
        
    return filepath, duration

def generate_audio(parsed_script: List[Dict[str, Any]], config: Dict[str, Any], output_dir: str = "output", progress_callback: Optional[Callable[[float], None]] = None) -> List[Dict[str, Any]]:
    """
    2. Audio Generation Logic
    Generates TTS audio for each line using Google Cloud TTS.
    """
    logger.info("Initializing TTS Client...")
    
    updated_script = []
    total_lines = len(parsed_script)
    
    for i, line in enumerate(parsed_script):
        speaker = line.get('speaker')
        text = line.get('text')
        
        if not speaker or not text:
            updated_script.append(line)
            continue
            
        filepath, duration = generate_single_audio(text, speaker, i, config, output_dir=output_dir)
        
        if filepath:
            line['audio_file'] = filepath
            line['audio_path'] = filepath
            line['duration'] = duration
        
        updated_script.append(line)
        
        if progress_callback:
            progress_callback((i + 1) / total_lines)
            
    return updated_script

def generate_frames(parsed_script: List[Dict[str, Any]], roster: List[str], config: Dict[str, Any], output_dir: str = "output", progress_callback: Optional[Callable[[float], None]] = None) -> List[Dict[str, Any]]:
    """
    3. Visual Generation Logic (Vertical Ensemble)
    """
    logger.info("Starting visual generation...")
    
    os.makedirs(output_dir, exist_ok=True)
    
    video_width = 1080
    video_height = 1920
    settings = config.get('settings', {})
    bg_color = settings.get('background_color', '#FFFFFF')
    
    # Load Font
    font_path = settings.get('font_path', 'arial.ttf')
    try:
        font = ImageFont.truetype(font_path, settings.get('font_size', 50))
    except IOError:
        logger.warning(f"Could not load font {font_path}, using default.")
        font = ImageFont.load_default()

    # Load Balloon
    balloon_path = settings.get('balloon_image', 'assets/balloon.png')
    try:
        balloon_img = Image.open(balloon_path).convert("RGBA")
        b_target_width = int(video_width * 0.9)
        b_ratio = b_target_width / balloon_img.width
        b_target_height = int(balloon_img.height * b_ratio)
        balloon_img = balloon_img.resize((b_target_width, b_target_height), Image.Resampling.LANCZOS)
    except FileNotFoundError:
        logger.error(f"Balloon image not found at {balloon_path}")
        return parsed_script

    # Pre-load and Normalize Roster Images
    target_char_height = 900
    roster_images = {}
    
    for char_name in roster:
        char_conf = config.get('characters', {}).get(char_name)
        if char_conf and 'image' in char_conf:
            img_path = char_conf['image']
            try:
                img = Image.open(img_path).convert("RGBA")
                width_percent = (target_char_height / float(img.size[1]))
                new_width = int((float(img.size[0]) * float(width_percent)))
                img = img.resize((new_width, target_char_height), Image.Resampling.LANCZOS)
                roster_images[char_name] = img
            except Exception as e:
                logger.warning(f"Could not load image for {char_name}: {e}")
        else:
            logger.warning(f"No image config found for {char_name}")

    if not roster_images:
        logger.error("No character images loaded! Check assets.")
        # Proceeding might be dangerous, but caller handles return
        return parsed_script

    total_lines = len(parsed_script)

    # Layout Calculation
    BUFFER_SPACE = 50
    total_stack_height = balloon_img.height + BUFFER_SPACE + target_char_height
    balloon_y = (video_height - total_stack_height) // 2
    char_y_top = balloon_y + balloon_img.height + BUFFER_SPACE

    for i, line in enumerate(parsed_script):
        speaker = line.get('speaker')
        text_content = line.get('text', "")
        
        frame = Image.new('RGBA', (video_width, video_height), bg_color)
        
        # --- Stage Layer ---
        num_chars = len(roster)
        if num_chars > 0:
            slot_width = video_width // num_chars
            max_char_width = int(slot_width * 0.95)
            
            for idx, char_name in enumerate(roster):
                if char_name not in roster_images:
                    continue
                
                char_img = roster_images[char_name].copy()
                
                if char_img.width > max_char_width:
                     ratio = max_char_width / float(char_img.width)
                     new_h = int(char_img.height * ratio)
                     char_img = char_img.resize((max_char_width, new_h), Image.Resampling.LANCZOS)

                current_speaker_key = resolve_character_key(speaker, config)
                is_active = (current_speaker_key == char_name)
                is_narrator = (speaker == "Narrator")
                
                if is_narrator or not is_active:
                     alpha = char_img.split()[3]
                     alpha = alpha.point(lambda p: p * 0.5)
                     char_img.putalpha(alpha)
                
                slot_center_x = (idx * slot_width) + (slot_width // 2)
                img_w, img_h = char_img.size
                paste_x = slot_center_x - (img_w // 2)
                paste_y = char_y_top

                frame.paste(char_img, (paste_x, paste_y), char_img)

        # --- Dialogue Layer ---
        balloon_x = (video_width - balloon_img.width) // 2
        frame.paste(balloon_img, (balloon_x, balloon_y), balloon_img)
        
        draw = ImageDraw.Draw(frame)
        wrapper = textwrap.TextWrapper(width=30) 
        wrapped_text = wrapper.fill(text=text_content)
        
        left, top, right, bottom = draw.textbbox((0, 0), wrapped_text, font=font)
        text_width = right - left
        text_height = bottom - top
        
        balloon_center_x = video_width // 2
        balloon_center_y = balloon_y + (balloon_img.height // 2)
        
        text_x = balloon_center_x - (text_width // 2)
        text_y = balloon_center_y - (text_height // 2)
        text_color = "#000000"
        
        draw.multiline_text(
            (text_x, text_y), 
            wrapped_text, 
            fill=text_color, 
            font=font, 
            align="center"
        )
        
        frame_filename = f"frame_{i}.png"
        frame_path = os.path.join(output_dir, frame_filename)
        frame.save(frame_path)
        
        line['image_path'] = frame_path
        
        if progress_callback:
            progress_callback((i + 1) / total_lines)

    return parsed_script

def assemble_video(parsed_script: List[Dict[str, Any]], output_dir: str = "output", output_filename: str = "final_video.mp4", progress_callback: Optional[Callable[[float], None]] = None) -> Optional[str]:
    """
    4. Assembly Logic
    Combines frames and audio into video segments, then concatenates them.
    """
    logger.info("Starting video assembly...")
    
    temp_dir = os.path.join(output_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    
    segment_files = []
    total_lines = len(parsed_script)
    
    for i, line in enumerate(parsed_script):
        image_path = line.get('image_path')
        audio_path = line.get('audio_file') or line.get('audio_path')
        
        if not image_path or not audio_path:
            logger.warning(f"Skipping line {i} due to missing assets. Image: {image_path}, Audio: {audio_path}")
            continue
            
        segment_filename = f"segment_{i}.mp4"
        segment_path = os.path.join(temp_dir, segment_filename)
        segment_path = os.path.abspath(segment_path)
        image_path = os.path.abspath(image_path)
        audio_path = os.path.abspath(audio_path)
        
        try:
            input_image = ffmpeg.input(image_path, loop=1)
            input_audio = ffmpeg.input(audio_path)
            
            stream = ffmpeg.output(
                input_image, 
                input_audio, 
                segment_path, 
                vcodec='libx264', 
                acodec='aac', 
                pix_fmt='yuv420p', 
                shortest=None,
                tune='stillimage'
            )
            
            stream.run(overwrite_output=True, quiet=True)
            segment_files.append(segment_path)
            
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg Error on segment {i}: {e.stderr.decode() if e.stderr else str(e)}")
            continue
        except Exception as e:
            logger.error(f"Error creating segment {i}: {e}", exc_info=True)
            continue
            
        if progress_callback:
            progress_callback((i + 1) / total_lines)
        
    if not segment_files:
        logger.error("No segments created.")
        return None
        
    final_output = os.path.join(output_dir, output_filename)
    final_output = os.path.abspath(final_output)
    
    logger.info(f"Concatenating {len(segment_files)} segments...")
    
    try:
        list_path = os.path.join(temp_dir, "file_list.txt")
        with open(list_path, 'w') as f:
            for seg in segment_files:
                f.write(f"file '{seg.replace(os.sep, '/')}'\n")
                
        (
            ffmpeg
            .input(list_path, format='concat', safe=0)
            .output(final_output, c='copy')
            .run(overwrite_output=True, quiet=True)
        )
        
        return final_output
        
    except ffmpeg.Error as e:
        logger.error(f"FFmpeg Concat Error: {e.stderr.decode() if e.stderr else str(e)}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Error assembling video: {e}", exc_info=True)
        return None

def create_separator_clip(config: Dict[str, Any], output_dir: str = "output"):
    """
    Creates the 'Check your understanding...' separator clip.
    Returns an ImageClip (1.0s).
    """
    filename = "separator.png"
    filepath = os.path.join(output_dir, filename)
    filepath = os.path.abspath(filepath)
    
    width, height = 1080, 1920
    img = Image.new('RGB', (width, height), color='black')
    draw = ImageDraw.Draw(img)
    
    settings = config.get('settings', {})
    font_path = settings.get('font_path', 'arial.ttf')
    try:
        font = ImageFont.truetype(font_path, 80)
    except:
        font = ImageFont.load_default()
        
    text = "Check your understanding..."
    
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    text_w = right - left
    text_h = bottom - top
    x = (width - text_w) // 2
    y = (height - text_h) // 2
    
    draw.text((x, y), text, font=font, fill="white")
    img.save(filepath)
    
    if os.path.exists(filepath):
        clip = ImageClip(filepath).with_duration(1.0)
        return clip
    return None

def add_background_music(video_clip, assets_dir: str = "assets"):
    """
    Adds background music to a video clip.
    """
    if not os.path.exists(assets_dir):
        return video_clip

    music_files = [f for f in os.listdir(assets_dir) if f.lower().endswith(".mp3")]
    
    if not music_files:
        logger.warning("No background music found in assets/")
        return video_clip
        
    bg_music_name = random.choice(music_files)
    bg_music_path = os.path.join(assets_dir, bg_music_name)
    logger.info(f"Adding background music: {bg_music_name}")
    
    try:
        music = AudioFileClip(bg_music_path)
        music = music.with_effects([AudioLoop(duration=video_clip.duration)])
        music = music.with_volume_scaled(0.12)
        
        if video_clip.duration > 2:
             music = music.with_effects([AudioFadeOut(duration=2.0)])
             
        original_audio = video_clip.audio
        if original_audio:
            final_audio = CompositeAudioClip([original_audio, music])
        else:
            final_audio = music
            
        video_clip.audio = final_audio
        return video_clip
        
    except Exception as e:
        logger.error(f"Failed to add background music: {e}", exc_info=True)
        return video_clip

def cleanup_workspace():
    """
    Deletes temporary directories and files used during generation.
    """
    logger.info("Starting workspace cleanup...")
    
    dirs_to_clean = [
        os.path.join("output", "temp"),
        os.path.join("output", "frames_web"),
        os.path.join("output", "frames_listening"),
        os.path.join("output", "frames_reading"),
        "temp"
    ]
    
    for d in dirs_to_clean:
        if os.path.exists(d):
            try:
                shutil.rmtree(d, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Failed to remove {d}: {e}")
                
    output_dir = "output"
    if os.path.exists(output_dir):
        files = os.listdir(output_dir)
        for f in files:
            if f.startswith("audio_") and f.endswith(".mp3"):
                file_path = os.path.join(output_dir, f)
                try:
                    os.remove(file_path)
                except Exception as e:
                    logger.warning(f"Failed to remove {file_path}: {e}")

def create_title_card(text: str, config: Dict[str, Any]) -> str:
    """
    Creates the title card for the Web Video.
    """
    logger.info("Creating Title Card...")
    output_path = os.path.join("output", "temp", "title_card.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    bg_path = "assets/lesson.png"
    target_size = (1080, 1920)
    
    try:
        if os.path.exists(bg_path):
            img = Image.open(bg_path).convert("RGB")
            img = ImageOps.fit(img, target_size, method=Image.Resampling.LANCZOS)
        else:
             logger.warning(f"{bg_path} not found. Using white background.")
             img = Image.new("RGB", target_size, "white")
    except Exception as e:
        logger.error(f"Error loading {bg_path}: {e}")
        img = Image.new("RGB", target_size, "white")
        
    draw = ImageDraw.Draw(img)
    
    settings = config.get('settings', {})
    font_path = settings.get('font_path', 'arial.ttf')
    font_size = 100 
    try:
        font = ImageFont.truetype(font_path, font_size)
    except:
        font = ImageFont.load_default()
        
    avg_char_width = font_size * 0.5
    chars_per_line = int(864 / avg_char_width)
    if chars_per_line < 10: chars_per_line = 10
    
    wrapper = textwrap.TextWrapper(width=chars_per_line)
    wrapped_text = wrapper.fill(text)
    
    left, top, right, bottom = draw.textbbox((0, 0), wrapped_text, font=font, align="center")
    text_w = right - left
    text_h = bottom - top
    
    x = (target_size[0] - text_w) // 2
    y = (target_size[1] - text_h) // 2
    
    draw.multiline_text((x, y), wrapped_text, font=font, fill="#333333", align="center")
    
    img.save(output_path)
    return output_path

def create_social_title_img(text: str, config: Dict[str, Any]) -> str:
    """
    Creates a transparent overlay with the lesson title for Social Video.
    """
    logger.info("Creating Social Title Overlay...")
    output_path = os.path.join("output", "temp", "social_title_overlay.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    width, height = 1080, 1920
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    settings = config.get('settings', {})
    font_path = settings.get('font_path', 'arial.ttf')
    font_size = 90
    try:
        font = ImageFont.truetype(font_path, font_size)
    except:
        font = ImageFont.load_default()

    avg_char_width = font_size * 0.5
    chars_per_line = int((width * 0.9) / avg_char_width)
    wrapper = textwrap.TextWrapper(width=chars_per_line)
    wrapped_text = wrapper.fill(text)

    left, top, right, bottom = draw.textbbox((0, 0), wrapped_text, font=font, align="center")
    text_w = right - left
    text_h = bottom - top

    x = (width - text_w) // 2
    y = 1100

    draw.multiline_text(
        (x, y), 
        wrapped_text, 
        font=font, 
        fill="white", 
        align="center",
        stroke_width=6,
        stroke_fill="black"
    )

    img.save(output_path)
    return output_path
