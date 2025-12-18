import streamlit as st
import json
import os
from dotenv import load_dotenv

import logging
import time

# Load environment variables
load_dotenv()

# Logger Setup
def setup_logging(debug_mode=False):
    level = logging.DEBUG if debug_mode else logging.INFO
    
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Check if handlers already exist to avoid duplicates
    if not logger.handlers:
        # File Handler
        file_handler = logging.FileHandler('app.log')
        file_handler.setLevel(level)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Optional: Console Handler (Streamlit prints to console anyway, but good for cleanliness)
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

# Load configuration
import google.generativeai as genai
from google.cloud import texttospeech
from mutagen.mp3 import MP3
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance
import textwrap
import uuid
import ffmpeg
import shutil
import edge_tts
import copy
import asyncio
import random
from moviepy import ImageClip, CompositeVideoClip, ColorClip, concatenate_videoclips, AudioFileClip, VideoFileClip, CompositeAudioClip
from moviepy.audio.fx import AudioLoop, AudioFadeOut
from bs4 import BeautifulSoup
import re
from vocab_functions import generate_vocab_assets, create_vocab_video_sequence

logger = logging.getLogger(__name__)

# Load configuration
def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        st.error("config.json not found.")
        logger.error("config.json not found.")
        return {}

config = load_config()

# --- Placeholder Functions ---

def generate_dual_scripts(raw_text):
    """
    Step 1 & 2: Dual Brain Logic
    Generates TWO scripts:
    1. Social Script (Fast-paced, dialogue only)
    2. Web Script (Verbatim, full structure)
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        st.error("GEMINI_API_KEY not found in environment variables.")
        logger.error("GEMINI_API_KEY not found.")
        return [], []

    social_script = []
    web_script = []

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(config['gemini_model'])

        # --- CALL A: SOCIAL SCRIPT ---
        # logger.info("Generating Social Script (Call A)...") 
        # (Disabled in favor of Truncated Web Script Strategy)
        # ... [Previous Social Prompt Code Commented Out by User Request] ...
        
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
        st.error(f"Error generating dual scripts: {e}")
        logger.error(f"Error generating dual scripts: {e}", exc_info=True)
        return [], []

# --- Helper Functions ---

def resolve_character_key(name):
    """
    Robustly resolves a character name from the script to a key in config.json.
    Strategies:
    1. Exact Match
    2. Case-Insensitive Match
    3. Partial Match (Script Name contains Config Key) e.g. "Herbert Walker" -> "Herbert"
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
    # Useful if Script says "Herbert Walker" but Key is "Herbert"
    for key in valid_keys:
        if name.lower().startswith(key.lower()):
            return key
            
    # Strategy 4: Reverse Partial (Key starts with Name)
    # Useful if Script says "Herbert" but Key is "Herbert Walker"
    for key in valid_keys:
        if key.lower().startswith(name.lower()):
            return key
            
    return None

def get_active_roster(parsed_script):
    """
    1. Roster Logic
    Extracts unique char names (excluding Narrator) to determine who is on stage.
    """
    roster = set()
    valid_characters = config.get('characters', {}).keys()
    
    for line in parsed_script:
        speaker = line.get('speaker')
        if speaker and speaker != "Narrator":
            resolved_key = resolve_character_key(speaker)
            if resolved_key:
                roster.add(resolved_key) # Store the Config Key, not the Script Name
    
    return list(roster)

def clean_html_content(raw_html):
    """
    Step 0: Clean HTML Content
    Extracts English dialogue from specific lesson structures.
    """
    soup = BeautifulSoup(raw_html, 'html.parser')
    
    # Step 0: Extract Vocabulary (before cleaning destroys structure)
    vocab_list = extract_vocabulary(soup)
    
    # Step 0.5: Extract Lesson Title
    lesson_title_tag = soup.find('h2')
    lesson_title = lesson_title_tag.get_text(strip=True) if lesson_title_tag else "Untitled Lesson"

    # Step A: Locate Content
    # Look for vocabulary story OR grammar dialogue
    section = soup.find('section', class_='vocabulary-story')
    if not section:
        section = soup.find('section', class_='dialogue')
    
    # Fallback to body or full soup if specific sections not found
    target_content = section if section else (soup.body if soup.body else soup)

    # Get inner string content to apply regex
    # decode_contents() gets the inner HTML as string
    if hasattr(target_content, 'decode_contents'):
        text = target_content.decode_contents()
    else:
        text = str(target_content)

    # Step B: Cleaning
    
    # 1. Newlines: <br> -> \n
    # Handle <br>, <br/>, <br />
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    
    # 2. Remove Italian Translations: [tooltip]...[/tooltip]
    # Remove the tag and everything inside it, replacing with a space to prevent merging
    text = re.sub(r'\[tooltip\].*?\[/tooltip\]', ' ', text, flags=re.DOTALL)
    
    # 3. Remove Custom Tags: [esempio] and [/esempio]
    # Keep the content inside, just remove tags, replacing with space
    text = re.sub(r'\[/?esempio\]', ' ', text)
    
    # 4. Strip HTML tags (including bold, italics etc.)
    # We parse the modified text again to strip remaining tags safely
    # This also helps handle entity decoding if any
    temp_soup = BeautifulSoup(text, 'html.parser')
    # Use separator to prevent "I am<b>thirty</b>" -> "I amthirty"
    final_text = temp_soup.get_text(separator=' ')
    
    # Clean up excessive whitespace created by separator
    final_text = re.sub(r'\s+', ' ', final_text).strip()
    
    return final_text, vocab_list, lesson_title

def extract_vocabulary(soup):
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
        # Content: <strong>Translate:</strong> sud
        trans_elem = card.find('div', class_='vocab-card-translate')
        translation = ""
        if trans_elem:
            raw_trans = trans_elem.get_text(separator=' ', strip=True) # "Translate: sud"
            # Remove "Translate:" prefix (case insensitive, handle bold tag text too)
            # Regex to remove "Translate:" or "Translate" and any following colon/space
            translation = re.sub(r'^Translate:?\s*', '', raw_trans, flags=re.IGNORECASE)
            translation = re.sub(r'\s+', ' ', translation).strip()
            
        # 3. Example
        # Content: <strong>Example:</strong> He looked south...
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

def generate_single_audio(text, speaker, index, output_dir="output"):
    """
    Step 2a: Generate Audio
    - Uses Google Cloud TTS
    - Returns filename and duration
    """
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Init Client logic checks
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        # Just a warning, it might be in system env
        pass

    try:
        client = texttospeech.TextToSpeechClient()
    except Exception as e:
        st.error(f"Failed to initialize TTS client: {e}")
        logger.error(f"Failed to initialize TTS client: {e}", exc_info=True)
        return None, 0.0

    # Determine Voice Params
    voice_params = None
    if speaker == "Narrator":
        voice_params = config.get('narrator', {}).get('voice_params')
    else:
        # Check specific character using robust lookup
        resolved_key = resolve_character_key(speaker)
        if resolved_key:
            char_config = config.get('characters', {}).get(resolved_key)
            if char_config:
                voice_params = char_config.get('voice_params')

    if not voice_params:
        # Fallback to Narrator if character not found 
        voice_params = config.get('narrator', {}).get('voice_params') 
    
    if not voice_params:
         st.error(f"Critical: No voice params found for {speaker} and no default narrator config.")
         logger.critical(f"No voice params found for {speaker} and no default narrator config.")
         return None, 0.0

    # Prepare Request
    synthesis_input = texttospeech.SynthesisInput(text=text)
    
    # Select Voice
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

    # Select Audio Config
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )

    try:
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
    except Exception as e:
        st.error(f"TTS API Error for {speaker}: {e}")
        logger.error(f"TTS API Error for {speaker}: {e}", exc_info=True)
        return None, 0.0

    # Save File
    # output/audio_{index}.mp3
    filename = f"audio_{index}.mp3"
    filepath = os.path.join(output_dir, filename)
    
    filepath = os.path.abspath(filepath) 

    with open(filepath, "wb") as out:
        out.write(response.audio_content)
        
    # Get Duration
    try:
        audio = MP3(filepath)
        duration = audio.info.length
    except Exception as e:
        st.warning(f"Could not determine duration for {filepath}: {e}")
        logger.warning(f"Could not determine duration for {filepath}: {e}")
        duration = 0.0
        
    return filepath, duration

def generate_audio(parsed_script, output_dir="output"):
    """
    2. Audio Generation Logic
    Generates TTS audio for each line using Google Cloud TTS.
    """
    st.info("Initializing TTS Client...")
    
    updated_script = []
    
    total_lines = len(parsed_script)
    progress_bar = st.progress(0)
    
    for i, line in enumerate(parsed_script):
        speaker = line.get('speaker')
        text = line.get('text')
        
        if not speaker or not text:
            updated_script.append(line)
            continue
            
        # Call helper
        filepath, duration = generate_single_audio(text, speaker, i, output_dir=output_dir)
        
        if filepath:
            line['audio_file'] = filepath
            line['audio_path'] = filepath # Setting both for compatibility
            line['duration'] = duration
        
        updated_script.append(line)
        progress_bar.progress((i + 1) / total_lines)
            
    return updated_script

def generate_frames(parsed_script, roster, output_dir="output"):
    """
    3. Visual Generation Logic (Vertical Ensemble)
    """
    st.info("Step 3: Generating Visuals...")
    logger.info("Starting visual generation...")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Config & Assets Setup
    video_width = 1080
    video_height = 1920
    bg_color = config['settings'].get('background_color', '#FFFFFF')
    
    # Load Font
    font_path = config['settings'].get('font_path', 'arial.ttf')
    try:
        # Try loading font, fallback to default if fails
        font = ImageFont.truetype(font_path, config['settings'].get('font_size', 50))
    except IOError:
        st.warning(f"Could not load font {font_path}, using default.")
        logger.warning(f"Could not load font {font_path}, using default.")
        font = ImageFont.load_default()

    # Load Balloon
    balloon_path = config['settings'].get('balloon_image', 'assets/balloon.png')
    try:
        balloon_img = Image.open(balloon_path).convert("RGBA")
        # Resize balloon to fit width with some padding
        b_target_width = int(video_width * 0.9)
        b_ratio = b_target_width / balloon_img.width
        b_target_height = int(balloon_img.height * b_ratio)
        balloon_img = balloon_img.resize((b_target_width, b_target_height), Image.Resampling.LANCZOS)
    except FileNotFoundError:
        st.error(f"Balloon image not found at {balloon_path}")
        logger.error(f"Balloon image not found at {balloon_path}")
        return parsed_script

    # 2. Pre-load and Normalize Roster Images (Safeguard 1)
    target_char_height = 900
    roster_images = {}
    
    for char_name in roster:
        # Look up image path in config
        char_conf = config['characters'].get(char_name)
        if char_conf and 'image' in char_conf:
            img_path = char_conf['image']
            try:
                img = Image.open(img_path).convert("RGBA")
                
                # Resize maintaining aspect ratio
                width_percent = (target_char_height / float(img.size[1]))
                new_width = int((float(img.size[0]) * float(width_percent)))
                img = img.resize((new_width, target_char_height), Image.Resampling.LANCZOS)
                
                roster_images[char_name] = img
            except Exception as e:
                st.warning(f"Could not load image for {char_name}: {e}")
                logger.warning(f"Could not load image for {char_name}: {e}")
        else:
            st.warning(f"No image config found for {char_name}")

    if not roster_images:
        st.error("No character images loaded! Check assets.")
        return parsed_script

    total_lines = len(parsed_script)
    progress_bar = st.progress(0)

    # --- Vertical Layout Calculation (Center-Out) ---
    BUFFER_SPACE = 50
    # Total height = Balloon + Buffer + Character (normalized)
    total_stack_height = balloon_img.height + BUFFER_SPACE + target_char_height
    
    # Calculate Top Y to center the whole stack
    balloon_y = (video_height - total_stack_height) // 2
    
    # Character starts below balloon + buffer
    char_y_top = balloon_y + balloon_img.height + BUFFER_SPACE


    # 3. Generate Frames Loop
    for i, line in enumerate(parsed_script):
        speaker = line.get('speaker')
        text_content = line.get('text', "")
        
        # Create Canvas
        frame = Image.new('RGBA', (video_width, video_height), bg_color)
        
        # --- Stage Layer (Bottom) ---
        # Safeguard 2: Distribute evenly
        num_chars = len(roster)
        if num_chars > 0:
            # Calculate positions
            # Divide width into slots
            slot_width = video_width // num_chars
            
            # Max width per character (leave some margin)
            max_char_width = int(slot_width * 0.95)
            
            for idx, char_name in enumerate(roster):
                if char_name not in roster_images:
                    continue
                
                char_img = roster_images[char_name].copy()
                
                # Resize if wider than slot
                if char_img.width > max_char_width:
                     ratio = max_char_width / float(char_img.width)
                     new_h = int(char_img.height * ratio)
                     char_img = char_img.resize((max_char_width, new_h), Image.Resampling.LANCZOS)

                # Safeguard 3: Opacity Logic
                # If Narrator is speaking, EVERYONE is 50%
                # If Character is speaking, they are 100%, others 50%
                
                # Robustly check if this character is the active speaker
                # We need to resolve the current line's speaker to a config key
                current_speaker_key = resolve_character_key(speaker)
                
                is_active = (current_speaker_key == char_name)
                is_narrator = (speaker == "Narrator")
                
                if is_narrator or not is_active:
                     # Reduce opacity to 50%
                     # Get alpha channel, multiply by 0.5
                     alpha = char_img.split()[3]
                     alpha = alpha.point(lambda p: p * 0.5)
                     char_img.putalpha(alpha)
                
                # Safeguard 2: Layout (Center-Out)
                # Calculate center of the slot
                slot_center_x = (idx * slot_width) + (slot_width // 2)
                
                # Position image relative to the calculated char_y_top
                img_w, img_h = char_img.size
                paste_x = slot_center_x - (img_w // 2)
                
                # Align top of character to the calculated line:
                paste_y = char_y_top

                # Paste
                frame.paste(char_img, (paste_x, paste_y), char_img)

        # --- Dialogue Layer (Top) ---
        # 1. Draw Order (CRITICAL): Paste Balloon FIRST
        balloon_x = (video_width - balloon_img.width) // 2
        # balloon_y is already calculated before the loop
        frame.paste(balloon_img, (balloon_x, balloon_y), balloon_img)
        
        # 2. Initialize Draw Object AFTER pasting
        draw = ImageDraw.Draw(frame)
        
        # Wrap Text
        # Heuristic: pixels to chars ratio... simplified.
        wrapper = textwrap.TextWrapper(width=30) 
        wrapped_text = wrapper.fill(text=text_content)
        
        # 3. Visual Fail-safes & Centering
        # Calculate text size
        left, top, right, bottom = draw.textbbox((0, 0), wrapped_text, font=font)
        text_width = right - left
        text_height = bottom - top
        
        # Visual Fail-safe: Recalculate center
        # Text Center Y should match Balloon Center Y
        balloon_center_x = video_width // 2
        balloon_center_y = balloon_y + (balloon_img.height // 2)
        
        text_x = balloon_center_x - (text_width // 2)
        text_y = balloon_center_y - (text_height // 2)
        
        # Visual Fail-safe: Force Color to BLACK
        text_color = "#000000"
        
        # Coordinate Debugging
        logger.debug(f"Frame {i}: Balloon Y={balloon_y}, Text Y={text_y}, Color={text_color}")
        
        # Draw Text
        draw.multiline_text(
            (text_x, text_y), 
            wrapped_text, 
            fill=text_color, 
            font=font, 
            align="center"
        )
        
        # Save Frame
        frame_filename = f"frame_{i}.png"
        frame_path = os.path.join(output_dir, frame_filename)
        frame.save(frame_path)
        
        line['image_path'] = frame_path
        progress_bar.progress((i + 1) / total_lines)

    return parsed_script

def assemble_video(parsed_script, output_dir="output", output_filename="final_video.mp4"):
    """
    4. Assembly Logic
    Combines frames and audio into video segments, then concatenates them.
    """
    st.info("Step 4: Assembling Video...")
    logger.info("Starting video assembly...")
    
    temp_dir = os.path.join(output_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    
    segment_files = []
    
    total_lines = len(parsed_script)
    progress_bar = st.progress(0)
    
    for i, line in enumerate(parsed_script):
        image_path = line.get('image_path')
        audio_path = line.get('audio_file') # Note: generate_audio used 'audio_path' or 'audio_file'? Let's check... it used 'audio_path', but verify app.py.
        # Wait, the previous generate_audio code I wrote used `line['audio_path'] = filepath`?
        # Let's check the code I wrote in app.py Step Id 191... 
        # Ah, in Step 131 I wrote: line['audio_path'] = filepath
        # But in Step 191 I wrote: line['audio_file'] = filepath inside generate_video loop but generate_audio inside?
        # Actually, let's look at generate_audio in app.py from Step 132/191.
        # It seems I used `line['audio_path'] = filepath` in generate_audio.
        # But in `generate_video` loop in Step 189/191, I was simulating the loop? No, I called `generate_audio`.
        # I need to use the key that `generate_audio` sets.
        # Based on Step 132, it sets `line['audio_path']`. 
        # Wait, in Step 191 diff, I see in generate_video: `line['audio_file'] = filepath` inside the loop??
        # Ah, `generate_single_audio` was the old logic... 
        # In Step 191, I kept `generate_frames` but `generate_video` calls `generate_audio`.
        # `generate_audio` (Step 132) sets `audio_path`.
        
        # Correction: I should check what keys are actually set.
        # Step 132 `generate_audio`: `line['audio_path'] = filepath`
        # Step 191 `generate_video` calls `generate_audio`.
        # So I should use `audio_path`.
        
        # BUT, the code visible in Step 191 showed:
        # `line['audio_file'] = filepath` in the Generate Single Audio loop inside generate_video...
        # Wait, did I replace generate_audio with the single loop or not?
        # In Step 191 replace content: `def generate_frames` replaced `def generate_audio`???
        # No, `generate_frames` starts at `def generate_frames`.
        # It seems I might have messed up the `generate_audio` function existence if I blindly replaced.
        # Let's assume standard keys and I will fix if needed. I'll read line keys.
        
        audio_path = line.get('audio_path') or line.get('audio_file')
        duration = line.get('duration')
        
        if not image_path or not audio_path:
            st.warning(f"Skipping line {i} due to missing assets.")
            logger.warning(f"Skipping line {i} due to missing assets. Image: {image_path}, Audio: {audio_path}")
            continue
            
        segment_filename = f"segment_{i}.mp4"
        segment_path = os.path.join(temp_dir, segment_filename)
        segment_path = os.path.abspath(segment_path)
        image_path = os.path.abspath(image_path)
        audio_path = os.path.abspath(audio_path)
        
        try:
            # Create Segment: Image Loop + Audio
            # ffmpeg -loop 1 -i image.png -i audio.mp3 -c:v libx264 -t duration -c:a aac -pix_fmt yuv420p out.mp4
            
            # Using ffmpeg-python
            input_image = ffmpeg.input(image_path, loop=1)
            input_audio = ffmpeg.input(audio_path)
            
            # Duration is crucial. If we rely on 'shortest', it ends when audio ends.
            # Audio might be slightly longer/shorter than duration metadata?
            # Safest is to use audio length.
            
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
            
            # Overwrite if exists
            stream.run(overwrite_output=True, quiet=True)
            
            segment_files.append(segment_path)
            
        except ffmpeg.Error as e:
            st.error(f"FFmpeg Error on segment {i}: {e.stderr.decode() if e.stderr else str(e)}")
            logger.error(f"FFmpeg Error on segment {i}", exc_info=True)
            continue
        except Exception as e:
            st.error(f"Error creating segment {i}: {e}")
            logger.error(f"Error creating segment {i}: {e}", exc_info=True)
            continue
            
        progress_bar.progress((i + 1) / total_lines)
        
    # Concatenate Segments
    if not segment_files:
        st.error("No segments created.")
        logger.error("No segments created.")
        return None
        
    final_output = os.path.join(output_dir, output_filename)
    final_output = os.path.abspath(final_output)
    
    st.info(f"Concatenating {len(segment_files)} segments...")
    
    try:
        # Create a text file for concat demuxer (more robust for many files)
        list_path = os.path.join(temp_dir, "file_list.txt")
        with open(list_path, 'w') as f:
            for seg in segment_files:
                # FFmpeg concat file format: file 'path'
                # Path escaping is tricky. 
                f.write(f"file '{seg.replace(os.sep, '/')}'\n")
                
        # ffmpeg -f concat -safe 0 -i list.txt -c copy final.mp4
        (
            ffmpeg
            .input(list_path, format='concat', safe=0)
            .output(final_output, c='copy')
            .run(overwrite_output=True, quiet=True)
        )
        
        return final_output
        
    except ffmpeg.Error as e:
        st.error(f"FFmpeg Concat Error: {e.stderr.decode() if e.stderr else str(e)}")
        logger.error(f"FFmpeg Concat Error", exc_info=True)
        return None
    except Exception as e:
        st.error(f"Error assembling video: {e}")
        logger.error(f"Error assembling video: {e}", exc_info=True)
        return None

def create_separator_clip(output_dir="output"):
    """
    Creates the 'Check your understanding...' separator clip.
    Returns an ImageClip (1.0s).
    """
    filename = "separator.png"
    filepath = os.path.join(output_dir, filename)
    filepath = os.path.abspath(filepath)
    
    # Create Image using PIL
    width, height = 1080, 1920
    img = Image.new('RGB', (width, height), color='black')
    draw = ImageDraw.Draw(img)
    
    # Load Font - attempt to load a bold font or default large
    # We'll use the same font as app if possible, or default
    font_path = config['settings'].get('font_path', 'arial.ttf')
    try:
        font = ImageFont.truetype(font_path, 80) # Large size
    except:
        font = ImageFont.load_default()
        
    text = "Check your understanding..."
    
    # Center Text
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

def add_background_music(video_clip):
    """
    Adds background music to a video clip.
    Picks a random .mp3 from assets/, loops it, sets volume to 12%,
    and fades out at the end.
    """
    assets_dir = "assets"
    if not os.path.exists(assets_dir):
        return video_clip

    # Find Audio Files
    music_files = [f for f in os.listdir(assets_dir) if f.lower().endswith(".mp3")]
    
    if not music_files:
        st.warning("No background music found in assets/")
        return video_clip
        
    # Pick Random
    bg_music_name = random.choice(music_files)
    bg_music_path = os.path.join(assets_dir, bg_music_name)
    logger.info(f"Adding background music: {bg_music_name}")
    
    try:
        # Load Audio
        music = AudioFileClip(bg_music_path)
        
        # Loop if needed
        # We want the music to cover the full duration
        # MoviePy v2: use with_effects([AudioLoop(...)])
        music = music.with_effects([AudioLoop(duration=video_clip.duration)])
        
        # Set Volume (12%)
        music = music.with_volume_scaled(0.12)
        
        # Fade Out (2s)
        # Check if duration > 2s to avoid errors
        if video_clip.duration > 2:
             music = music.with_effects([AudioFadeOut(duration=2.0)])
             
        # Composite
        # If video already has audio, mix them.
        original_audio = video_clip.audio
        if original_audio:
            final_audio = CompositeAudioClip([original_audio, music])
        else:
            final_audio = music
            
        video_clip.audio = final_audio
        return video_clip
        
    except Exception as e:
        st.warning(f"Failed to add background music: {e}")
        logger.error(f"Failed to add background music: {e}", exc_info=True)
        return video_clip

def cleanup_workspace():
    """
    Deletes temporary directories and files used during generation.
    Targets: output/temp/, output/frames_*/, temp/, output/audio_*.mp3
    """
    logger.info("Starting workspace cleanup...")
    
    # 1. Directories to remove
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
                # logger.info(f"Removed directory: {d}")
            except Exception as e:
                logger.warning(f"Failed to remove {d}: {e}")
                
    # 2. Files to remove (audio_*.mp3 in output/)
    output_dir = "output"
    if os.path.exists(output_dir):
        files = os.listdir(output_dir)
        for f in files:
            # Pattern: audio_*.mp3
            if f.startswith("audio_") and f.endswith(".mp3"):
                file_path = os.path.join(output_dir, f)
                try:
                    os.remove(file_path)
                    # logger.info(f"Removed file: {f}")
                except Exception as e:
                    logger.warning(f"Failed to remove {file_path}: {e}")

def create_title_card(text):
    """
    Creates the title card for the Web Video.
    Input: The lesson title text.
    Logic: Load assets/lesson.png as background, draw centered text.
    Returns: Path to the generated image.
    """
    st.info("Creating Title Card...")
    output_path = os.path.join("output", "temp", "title_card.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # 1. Background
    bg_path = "assets/lesson.png"
    target_size = (1080, 1920)
    
    try:
        if os.path.exists(bg_path):
            img = Image.open(bg_path).convert("RGB")
            img = ImageOps.fit(img, target_size, method=Image.Resampling.LANCZOS)
        else:
             st.warning(f"{bg_path} not found. Using white background.")
             img = Image.new("RGB", target_size, "white")
    except Exception as e:
        logger.error(f"Error loading {bg_path}: {e}")
        img = Image.new("RGB", target_size, "white")
        
    draw = ImageDraw.Draw(img)
    
    # 2. Font (Large, Bold)
    font_path = config['settings'].get('font_path', 'arial.ttf')
    font_size = 100 
    try:
        font = ImageFont.truetype(font_path, font_size)
    except:
        font = ImageFont.load_default()
        
    # 3. Text Wrapping
    # Heuristic for char width (approx 0.5 * font_size)
    avg_char_width = font_size * 0.5
    # Max width = 80% of 1080 = 864 pixels
    chars_per_line = int(864 / avg_char_width)
    if chars_per_line < 10: chars_per_line = 10
    
    wrapper = textwrap.TextWrapper(width=chars_per_line)
    wrapped_text = wrapper.fill(text)
    
    # 4. Draw Centered
    left, top, right, bottom = draw.textbbox((0, 0), wrapped_text, font=font, align="center")
    text_w = right - left
    text_h = bottom - top
    
    x = (target_size[0] - text_w) // 2
    y = (target_size[1] - text_h) // 2
    
    # Color: Black/Dark Grey
    draw.multiline_text((x, y), wrapped_text, font=font, fill="#333333", align="center")
    
    img.save(output_path)
    return output_path

def create_social_title_img(text):
    """
    Creates a transparent overlay with the lesson title for Social Video.
    Style: White text, Black outline, Centered, Y=1100.
    """
    st.info("Creating Social Title Overlay...")
    output_path = os.path.join("output", "temp", "social_title_overlay.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 1. Canvas (Transparent)
    width, height = 1080, 1920
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 2. Font (Large & Bold)
    font_path = config['settings'].get('font_path', 'arial.ttf')
    font_size = 90
    try:
        font = ImageFont.truetype(font_path, font_size)
    except:
        font = ImageFont.load_default()

    # 3. Wrap Text (Safety)
    avg_char_width = font_size * 0.5
    chars_per_line = int((width * 0.9) / avg_char_width)
    wrapper = textwrap.TextWrapper(width=chars_per_line)
    wrapped_text = wrapper.fill(text)

    # 4. Position & Draw
    # Calculate text size
    left, top, right, bottom = draw.textbbox((0, 0), wrapped_text, font=font, align="center")
    text_w = right - left
    text_h = bottom - top

    x = (width - text_w) // 2
    y = 1100  # Approx 60% down

    # Draw with Stroke (Outline)
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

def format_time(seconds):
    """
    Helper to convert seconds into readable string (e.g., "1m 30s" or "45s").
    """
    m, s = divmod(int(seconds), 60)
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"

def generate_video(parsed_script):
    """
    Step 2: Generate Video (Modules B, C, D)
    Main orchestration loop.
    Updated for Listening Challenge Structure + Smart Timer & ETR.
    """
    status_text = st.empty()
    main_progress = st.progress(0)
    start_time = time.time()
    
    def update_status(progress, text):
        """
        Updates progress bar and status text with ETR.
        """
        elapsed = time.time() - start_time
        
        # Calculate ETR
        # progress is 0.0 to 1.0
        # Avoid division by zero
        if progress > 0.01:
            estimated_total = elapsed / progress
            remaining = estimated_total - elapsed
            if remaining < 0: remaining = 0
            
            elapsed_str = format_time(elapsed)
            remaining_str = format_time(remaining)
            
            display_text = f"{text} | ⏳ Elapsed: {elapsed_str} | 🏁 Est. Remaining: {remaining_str}"
        else:
            elapsed_str = format_time(elapsed)
            display_text = f"{text} | ⏳ Elapsed: {elapsed_str} | 🏁 Est. Remaining: Calculating..."
            
        status_text.text(display_text)
        main_progress.progress(progress)

    # --- Part 1: Social Video (0% - 60%) ---
    
    # 1. Active Roster
    update_status(0.02, "Step 1: Determining active roster...")
    roster = get_active_roster(parsed_script)
    st.write(f"Active Characters: {roster}")
    update_status(0.05, "Step 1: Roster determined.")
    
    # 2. Audio Generation (Shared)
    if not parsed_script:
        st.error("Script is empty.")
        return

    update_status(0.05, "Step 2: Generating Audio...")
    # This modifies parsed_script in place with audio paths
    parsed_script_with_audio = generate_audio(parsed_script)
    st.success(f"Audio generated for {len(parsed_script_with_audio)} lines.")
    update_status(0.15, "Step 2: Audio complete.")

    # --- Part A: Listening Part (Masked) ---
    update_status(0.15, "Step 3a: Generating Listening Part (Masked)...")
    
    # Deep copy to safe-guard original script
    listening_script = copy.deepcopy(parsed_script_with_audio)
    
    # Mask text
    for line in listening_script:
        if 'text' in line:
            line['text'] = "..... ? ....."
            
    # Generate Frames for Listening
    listening_frames_dir = os.path.join("output", "frames_listening")
    listening_script_with_visuals = generate_frames(listening_script, roster, output_dir=listening_frames_dir)
    update_status(0.30, "Step 3a: Listening Frames generated.")
    
    # Assemble Listening Part
    listening_video_path = assemble_video(listening_script_with_visuals, output_dir="output", output_filename="listening_part.mp4")
    if not listening_video_path:
        st.error("Failed to generate Listening Part video.")
        return
    st.success("Listening Part generated.")
    update_status(0.35, "Step 3a: Listening Part assembled.")

    # --- Part B: Reading Part (Normal) ---
    update_status(0.35, "Step 3b: Generating Reading Part (Normal)...")
    
    # Use original script (already has audio)
    reading_frames_dir = os.path.join("output", "frames_reading")
    reading_script_with_visuals = generate_frames(parsed_script_with_audio, roster, output_dir=reading_frames_dir)
    update_status(0.45, "Step 3b: Reading Frames generated.")
    
    # Assemble Reading Part
    reading_video_path = assemble_video(reading_script_with_visuals, output_dir="output", output_filename="reading_part.mp4")
    if not reading_video_path:
        st.error("Failed to generate Reading Part video.")
        return
    st.success("Reading Part generated.")
    update_status(0.50, "Step 3b: Reading Part assembled.")

    # --- Part C: Final Assembly ---
    update_status(0.50, "Step 5: Final Montage & Branding...")
    
    try:
        final_clips = []

        # 1. Intro
        intro_path = "assets/intro.mp4"
        if os.path.exists(intro_path):
            intro_clip = VideoFileClip(intro_path)
            # Resize/Crop to 1080x1920
            intro_clip = intro_clip.resized(new_size=(1080, 1920))
            final_clips.append(intro_clip)
        else:
            st.warning(f"Intro video not found at {intro_path}, skipping.")

        # 2. Listening Part
        listening_clip = VideoFileClip(listening_video_path)
        final_clips.append(listening_clip)

        # 3. Separator
        separator_clip = create_separator_clip(output_dir="output")
        if separator_clip:
             final_clips.append(separator_clip)
        else:
             st.warning("Could not create separator clip.")

        # 4. Reading Part
        reading_clip = VideoFileClip(reading_video_path)
        final_clips.append(reading_clip)
        
        # 5. Conditional Vocab
        enable_vocab = config.get("ENABLE_VOCAB_SECTION", True)
        if enable_vocab and 'vocab_list' in st.session_state and st.session_state.vocab_list:
            update_status(0.53, "Adding Vocabulary Section...")
            vocab_assets = generate_vocab_assets(st.session_state.vocab_list)
            if vocab_assets:
                vocab_clip = create_vocab_video_sequence(vocab_assets)
                if vocab_clip:
                    final_clips.append(vocab_clip)
                else:
                     st.error("Vocabulary Video Sequence failed (None).")
            else:
                 st.error("Vocabulary Assets failed (None).")
        
        # D. Concatenate All
        st.info(f"Concatenating {len(final_clips)} clips...")
        final_combined = concatenate_videoclips(final_clips)
        
        # E. Branding Overlay (Applied to the WHOLE sequence)
        overlay_path = "assets/NoBackground.png"
        if os.path.exists(overlay_path):
            try:
                overlay_clip = ImageClip(overlay_path)
                overlay_clip = overlay_clip.with_duration(final_combined.duration)
                overlay_clip = overlay_clip.with_position(('center', 'bottom'))
                
                final_combined = CompositeVideoClip([final_combined, overlay_clip])
                st.info("Branding Overlay Applied.")
            except Exception as e:
                st.warning(f"Overlay Error: {e}")
        else:
            st.warning("Overlay image not found (assets/NoBackground.png).")

        # F. Background Music (New Step)
        if config.get("ENABLE_MUSIC", False):
            update_status(0.55, "Adding Background Music...")
            st.info("Adding Background Music...")
            final_combined = add_background_music(final_combined)
        else:
            st.info("Skipping Background Music (Optional).")

        # F.5 Title Overlay (Social Flash)
        update_status(0.57, "Adding Title Overlay...")
        lesson_title = st.session_state.get('lesson_title', "Lesson")
        social_title_path = create_social_title_img(lesson_title)
        
        if os.path.exists(social_title_path):
            try:
                title_overlay = ImageClip(social_title_path).with_duration(1.0).with_start(0)
                final_combined = CompositeVideoClip([final_combined, title_overlay])
                st.info("Title Overlay Applied.")
            except Exception as e:
                st.warning(f"Failed to apply Title Overlay: {e}")

        # G. Export
        update_status(0.58, "Exporting Social Video...")
        final_output_path = os.path.abspath(os.path.join("output", "final_video_complete.mp4"))
        final_combined.write_videofile(
            final_output_path, 
            codec="libx264", 
            audio_codec="aac",
            logger=None 
        )
        
        st.success("Video Generation Sequence Complete!")
        st.video(final_output_path)

    except Exception as e:
        st.error(f"Critical Error in Montage/Export: {e}")
        logger.error(f"Critical Error in Montage/Export: {e}", exc_info=True)
    
    update_status(0.60, "Social Video Finished.")
    
    # --- STEP B: Web Video Generation (60% - 100%) ---
    if 'script_web' in st.session_state and st.session_state.script_web:
        st.markdown("---")
        st.header("Generating Web Video (Step B)...")
        update_status(0.61, "Initializing Web Video Generation...")
        
        web_script = copy.deepcopy(st.session_state.script_web)
        
        try:
            # 1. Roster for Web Script
            web_roster = get_active_roster(web_script)
            st.write(f"Web Active Characters: {web_roster}")
            
            # 2. Generate Assets
            # Audio
            update_status(0.70, "Generating Web Audio...")
            st.info("Generating Web Audio...")
            audio_output_dir = os.path.join("output", "audio_web")
            web_script_with_audio = generate_audio(web_script, output_dir=audio_output_dir)
            
            # Frames
            update_status(0.85, "Generating Web Visuals...")
            st.info("Generating Web Visuals...")
            frames_web_dir = os.path.join("output", "frames_web")
            web_script_with_visuals = generate_frames(web_script_with_audio, web_roster, output_dir=frames_web_dir)
            
            # 3. Assemble Story Clip (Narrator + Dialogue)
            update_status(0.90, "Assembling Web Story...")
            st.info("Assembling Web Story...")
            story_video_path = assemble_video(
                web_script_with_visuals, 
                output_dir="output", 
                output_filename="temp_web_story.mp4"
            )
            
            if story_video_path:
                # 4. Create Title Clip
                lesson_title = st.session_state.get('lesson_title', "Lesson")
                title_card_path = create_title_card(lesson_title)
                
                final_web_clips = []
                
                # Title Clip (3 seconds)
                if os.path.exists(title_card_path):
                    title_clip = ImageClip(title_card_path).with_duration(3.0)
                    final_web_clips.append(title_clip)
                
                # Story Clip
                story_clip = VideoFileClip(story_video_path)
                final_web_clips.append(story_clip)
                
                # Concatenate
                update_status(0.95, "Concatenating Web Video...")
                st.info("Concatenating Web Video...")
                final_web_video = concatenate_videoclips(final_web_clips)
                
                # 5. Export (Web Video)
                update_status(0.98, "Exporting Web Video...")
                web_output_path = os.path.abspath(os.path.join("output", "Web_Video.mp4"))
                final_web_video.write_videofile(
                    web_output_path,
                    codec="libx264",
                    audio_codec="aac",
                    logger=None
                )
                
                st.success("Web Video Generated Successfully!")
                st.video(web_output_path)
                update_status(1.0, "Process Finished!")
            else:
                st.error("Failed to assemble Web Story video.")
                
        except Exception as e:
            st.error(f"Error generating Web Video: {e}")
            logger.error(f"Error generating Web Video: {e}", exc_info=True)
            
    else:
        update_status(1.0, "Process Finished!")

    # --- Cleanup ---
    if not config.get('debug_mode', False):
        cleanup_workspace()
        st.toast("🧹 Temporary files cleaned up.")
        logger.info("Temporary files cleaned up.")
    else:
        st.toast("🐛 Debug Mode ON: Temporary files preserved.")
        logger.info("Debug Mode ON: Temporary files preserved.")

# --- Streamlit UI ---

def main():
    st.set_page_config(page_title="Visual Novel Video Generator")

    # Sidebar
    st.sidebar.title("VN Video Gen")
    
    # 0. Global Settings
    debug_mode = st.sidebar.checkbox("Debug Mode", value=False)
    config['debug_mode'] = debug_mode
    setup_logging(debug_mode)
    if debug_mode:
        st.sidebar.warning("Debug Mode Enabled: detailed logs in app.log")
    
    # Dev Tools
    st.sidebar.markdown("---")
    st.sidebar.subheader("Dev Tools")
    if st.sidebar.button("Test Audio Generation"):
         with st.spinner("Testing Audio..."):
            # Test with Narrator
            path_n, dur_n = generate_single_audio("This is a test of the narrator voice.", "Narrator", 999)
            if path_n:
                st.sidebar.audio(path_n)
                st.sidebar.success(f"Narrator: {dur_n:.2f}s")
            
            # Test with Character (if exists)
            char_name = next(iter(config.get('characters', {})), None)
            if char_name:
                path_c, dur_c = generate_single_audio(f"Hello, I am {char_name}.", char_name, 998)
                if path_c:
                    st.sidebar.audio(path_c)
                    st.sidebar.success(f"{char_name}: {dur_c:.2f}s")

    # Main Area
    st.title("Visual Novel Video Generator")

    # 1. HTML Input
    raw_html = st.text_area("Paste Lesson HTML", height=300, placeholder="Paste the full lesson HTML code here...")

    # Button to Clean
    if st.button("Clean & Preview Text"):
        with st.spinner("Cleaning HTML..."):
            cleaned_text, vocab_list, lesson_title = clean_html_content(raw_html)
            
            # 1. Update Cleaned Text
            st.session_state.cleaned_text_preview = cleaned_text
            st.session_state.cleaned_text_preview_widget = cleaned_text
            st.session_state.original_clean_text = cleaned_text
            
            # 2. Update Vocabulary & Title
            st.session_state.vocab_list = vocab_list
            st.session_state.lesson_title = lesson_title
            
            st.write(f"**Lesson Title:** {lesson_title}")
            
            # Simple Type Detection for Feedback
            if raw_html and "vocabulary-story" in raw_html:
                st.success("Detected: Vocabulary Lesson")
            elif raw_html and "dialogue" in raw_html:
                st.success("Detected: Grammar Dialogue")
            else:
                st.info("Using Fallback / Body content extraction")

    # 2. Preview & Generate Script
    if 'cleaned_text_preview' in st.session_state and st.session_state.cleaned_text_preview:
        
        # --- NEW: Vocabulary Editor ---
        if 'vocab_list' in st.session_state and st.session_state.vocab_list:
            st.subheader("Extracted Vocabulary")
            # Allow users to edit the extracted list
            edited_vocab = st.data_editor(
                st.session_state.vocab_list,
                num_rows="dynamic",
                key="vocab_editor"
            )
            st.session_state.vocab_list = edited_vocab
            st.write("---")
        
        st.subheader("Cleaned English Text")
        
        # Editable Text Area for Verification
        final_script_text = st.text_area(
            "Verify & Edit Text", 
            key='cleaned_text_preview_widget', 
            value=st.session_state.cleaned_text_preview,
            height=200
        )
        
        # 2a. Generate Social Script Button
        st.write("---")
        # 2a. Generate Dual Scripts Button
        st.write("---")
        if st.button("Step 2: Generate Web Script"):
             # Ensure we have the original text safely
             source_text = st.session_state.get('original_clean_text', final_script_text)
             
             with st.spinner("Generating Web Script..."):
                 social, web = generate_dual_scripts(source_text)
                 
                 if social:
                     st.session_state.script_social = social
                     st.session_state.parsed_script = social # Compatibility for Step 3 Video Gen
                 if web:
                     st.session_state.script_web = web
                     
                 if social and web:
                     st.success("Web Script Generated (Social Teaser Auto-Derived)!")
                 elif social:
                     st.warning("Only Social Script generated.")
                 elif web:
                     st.warning("Only Web Script generated.")
                 else:
                     st.error("Failed to generate scripts.")

        # Stacked Editors (Vertical Layout)
        if 'script_social' in st.session_state or 'script_web' in st.session_state:
            
            # st.subheader("Social Script (TikTok/Shorts)") 
            # (HIDDEN as per requirements - Derived from Web Script)
            
            st.subheader("Script Editor (Full Story)")
            if 'script_web' in st.session_state:
                # Use Full Width
                edited_web = st.data_editor(
                    st.session_state.script_web, 
                    num_rows="dynamic", 
                    key='web_editor',
                    use_container_width=True
                )
                st.session_state.script_web = edited_web
                
                # DERIVE Social Script for generation downstream (First 6 lines of Edited Web Script)
                st.session_state.script_social = edited_web[:6]
                st.session_state.parsed_script = st.session_state.script_social

    # Placeholder for session state to store parsed script
    if 'parsed_script' not in st.session_state:
        st.session_state.parsed_script = []
    
    if 'social_script_draft' not in st.session_state:
         # Initialize strictly empty or based on previous parses?
         # For now, just placeholder.
         pass

    # 3. Review & Edit (Legacy/Fallback view or just debug?)
    # Since we have the editor above, we might hide this or keep it as read-only debug?
    # User asked for "Output Display" -> "Display the script in an st.data_editor". 
    # I did that above.
    # The existing "Review & Edit" section at 731 uses 'parsed_script'.
    # I will modify it to be less redundant or just section 3.
    
    # Let's keep the Video Gen button section pure.

    # 4. Generate Video Button
    if 'script_social' in st.session_state and st.session_state.script_social:
        st.write("---")
        st.header("Step 3: Create Video")
        
        use_music = st.checkbox("Add Background Music 🎵", value=False)

        if st.button("Generate Video"):
            # Update Config
            config["ENABLE_MUSIC"] = use_music

            # Ensure parsed_script is set (it should be linked to social_script)
            if st.session_state.parsed_script:
                generate_video(st.session_state.parsed_script)
            else:
                st.error("Script seems empty despite passing checks.")
    else:
        st.divider()
        st.info('👆 Please generate the scripts above to unlock Video Creation.')

if __name__ == "__main__":
    main()
