import streamlit as st
import json
import os
from dotenv import load_dotenv

import logging

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
import edge_tts
import asyncio
from moviepy import ImageClip, CompositeVideoClip, ColorClip, concatenate_videoclips, AudioFileClip, VideoFileClip
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

def parse_script(raw_text):
    """
    Step 1: Parse Script (Module A - Gemini)
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        st.error("GEMINI_API_KEY not found in environment variables.")
        logger.error("GEMINI_API_KEY not found.")
        return []

    try:
        logger.info("Parsing script with Gemini...")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(config['gemini_model'])

        system_prompt = """
        You are an expert script parser for a video generation engine.
        Your task is to convert raw narrative text into a structured JSON list.
    
        **Output Format:**
        A list of objects: `[{"speaker": "Exact Character Name", "text": "Cleaned Dialogue content"}]`
    
        **Character Mapping Rules (STRICT):**
        - If the text mentions "Herbert", "Mr. Walker", or "Dad" -> Map speaker to: "Herbert"
        - If the text mentions "Margot", "Mrs. Walker", or "Mom" -> Map speaker to: "Margot"
        - If the text mentions "Brian" -> Map speaker to: "Brian"
        - If the text mentions "Laura" -> Map speaker to: "Laura"
        - If the text mentions "Molly" -> Map speaker to: "Molly"
        - If the text describes an action, scene, or context (no spoken words) -> Map speaker to: "Narrator"
    
        **Cleaning Rules:**
        1. Remove all speech tags (e.g., "he said", "Molly asks", "replied Brian").
        2. Remove quotation marks surrounding the dialogue.
        3. Keep the dialogue text exactly as spoken.
        4. For the "Narrator", keep the descriptive text intact.
    
        **Example Input:**
        Brian said, "I am hungry."
        Molly laughs. "Me too!"
    
        **Example Output:**
        [
        {"speaker": "Brian", "text": "I am hungry."},
        {"speaker": "Narrator", "text": "Molly laughs."},
        {"speaker": "Molly", "text": "Me too!"}
        ]
    
        Return ONLY the valid JSON. No markdown formatting.
        """
        
        full_prompt = f"{system_prompt}\n\nRAW TEXT:\n{raw_text}"
        
        response = model.generate_content(full_prompt)
        
        # simple cleanup for markdown code blocks if present
        text_response = response.text
        if text_response.startswith("```json"):
            text_response = text_response[7:]
        if text_response.startswith("```"):
            text_response = text_response[3:]
        if text_response.endswith("```"):
            text_response = text_response[:-3]
            
        parsed_data = json.loads(text_response)
        logger.info(f"Successfully parsed script. {len(parsed_data)} lines found.")
        return parsed_data
        
    except Exception as e:
        st.error(f"Error parsing script: {e}")
        logger.error(f"Error parsing script: {e}", exc_info=True)
        return []

def generate_social_script(raw_text):
    """
    Step 2: Generate Social Script (Module A2 - Gemini Adapter)
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        st.error("GEMINI_API_KEY not found.")
        logger.error("GEMINI_API_KEY not found.")
        return []

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(config['gemini_model'])

        system_prompt = """
You are a Script Editor for short-form educational videos (TikTok/Reels). INPUT: Raw English text from a lesson. GOAL: Convert this into a fast dialogue script.

RULES:

    REMOVE SPEECH TAGS: Delete "he said", "she asked", "Margot says". Convert strictly to direct speech.

    PRESERVE KEYWORDS: You MUST keep the specific vocabulary used in the text. Do not simplify "south" to "down" or "library" to "bookstore". The lesson depends on these exact words.

    CONDENSE NARRATION: Shorten long descriptions by the Narrator.

    CHARACTER MAPPING: Assign lines to: "Herbert", "Margot", "Brian", "Laura", or "Narrator".

OUTPUT: A JSON object with a single key social_script: [{"character": "Margot", "text": "Why are you looking south?"}, ...]
"""
        
        full_prompt = f"{system_prompt}\n\nRAW TEXT:\n{raw_text}"
        
        response = model.generate_content(full_prompt)
        
        text_response = response.text
        # Clean markdown
        if text_response.startswith("```json"):
            text_response = text_response[7:]
        if text_response.startswith("```"):
            text_response = text_response[3:]
        if text_response.endswith("```"):
            text_response = text_response[:-3]
            
        json_data = json.loads(text_response)
        social_script = json_data.get("social_script", [])
        
        # Normalization: Map 'character' to 'speaker' for app compatibility
        normalized_script = []
        for item in social_script:
             speaker = item.get("character")
             text = item.get("text")
             # Simple mapping if needed, or just pass through. 
             # App expects "speaker" key.
             normalized_script.append({"speaker": speaker, "text": text})
             
        return normalized_script

    except Exception as e:
        st.error(f"Error generating social script: {e}")
        logger.error(f"Error generating social script: {e}", exc_info=True)
        return []

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
    
    return final_text, vocab_list

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

def generate_single_audio(text, speaker, index):
    """
    Step 2a: Generate Audio
    - Uses Google Cloud TTS
    - Returns filename and duration
    """
    # Ensure output directory exists
    output_dir = "output"
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

def generate_audio(parsed_script):
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
        filepath, duration = generate_single_audio(text, speaker, i)
        
        if filepath:
            line['audio_file'] = filepath
            line['audio_path'] = filepath # Setting both for compatibility
            line['duration'] = duration
        
        updated_script.append(line)
        progress_bar.progress((i + 1) / total_lines)
            
    return updated_script

def generate_frames(parsed_script, roster):
    """
    3. Visual Generation Logic (Vertical Ensemble)
    """
    st.info("Step 3: Generating Visuals...")
    logger.info("Starting visual generation...")
    
    output_dir = "output"
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

def assemble_video(parsed_script):
    """
    4. Assembly Logic
    Combines frames and audio into video segments, then concatenates them.
    """
    st.info("Step 4: Assembling Video...")
    logger.info("Starting video assembly...")
    
    output_dir = "output"
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
        
    final_output = os.path.join(output_dir, "final_video.mp4")
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

def generate_video(parsed_script):
    """
    Step 2: Generate Video (Modules B, C, D)
    Main orchestration loop.
    """
    status_text = st.empty()
    main_progress = st.progress(0)
    
    # 1. Active Roster
    status_text.text("Step 1: Determining active roster...")
    roster = get_active_roster(parsed_script)
    st.write(f"Active Characters: {roster}")
    main_progress.progress(10)
    
    # 2. Audio Generation
    if parsed_script:
        status_text.text("Step 2: Generating Audio...")
        parsed_script_with_audio = generate_audio(parsed_script)
        st.success(f"Audio generated for {len(parsed_script_with_audio)} lines.")
        
        # 3. Visual Generation
        status_text.text("Step 3: Generating Visuals...")
        parsed_script_with_visuals = generate_frames(parsed_script_with_audio, roster)
        st.success("Visuals generated.")
        
        # 4. Assembly
        status_text.text("Step 4: Assembling Video...")
        final_video_path = assemble_video(parsed_script_with_visuals)
        
        if final_video_path:
            # 5. Robust Montage Logic (Intro + Main + [Vocab])
            status_text.text("Step 5: Final Montage & Branding...")
            
            try:
                # A. Prepare Intro
                intro_path = "assets/intro.mp4"
                if os.path.exists(intro_path):
                    intro_clip = VideoFileClip(intro_path)
                    # Resize/Crop to 1080x1920 to ensure match
                    # Using resize((1080, 1920)) forces exact dimensions, might stretch if aspect ratio differs
                    # But per user constraint: "Ensure intro_clip is resized/cropped to 1080x1920"
                    intro_clip = intro_clip.resized(new_size=(1080, 1920))
                else:
                    st.warning(f"Intro video not found at {intro_path}, skipping.")
                    intro_clip = None

                # B. Main Clip
                main_clip = VideoFileClip(final_video_path)
                
                # Start Clip List
                final_clips = []
                if intro_clip:
                    final_clips.append(intro_clip)
                final_clips.append(main_clip)
                
                # C. Conditional Vocab
                # Check Config AND Session State
                enable_vocab = config.get("ENABLE_VOCAB_SECTION", True)
                if enable_vocab and 'vocab_list' in st.session_state and st.session_state.vocab_list:
                    status_text.text("Adding Vocabulary Section...")
                    vocab_assets = generate_vocab_assets(st.session_state.vocab_list)
                    if vocab_assets:
                        vocab_clip = create_vocab_video_sequence(vocab_assets)
                        if vocab_clip:
                            final_clips.append(vocab_clip)
                        else:
                             st.error("Vocabulary Video Sequence failed (None).")
                    else:
                         st.error("Vocabulary Assets failed (None).")
                
                # D. Concatenate
                st.info(f"Concatenating {len(final_clips)} clips...")
                final_combined = concatenate_videoclips(final_clips)
                
                # E. Branding Overlay
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

                # F. Export
                combined_path = final_video_path.replace(".mp4", "_final.mp4")
                final_combined.write_videofile(
                    combined_path, 
                    codec="libx264", 
                    audio_codec="aac",
                    logger=None 
                )
                
                final_video_path = combined_path
                st.success("Video Generation Sequence Complete!")
                st.video(final_video_path)

            except Exception as e:
                st.error(f"Critical Error in Montage/Export: {e}")
                logger.error(f"Critical Error in Montage/Export: {e}", exc_info=True)
        else:
            st.error("Video Assembly Failed.")
    
    main_progress.progress(100)
    status_text.text("Process Finished.")

# --- Streamlit UI ---

def main():
    st.set_page_config(page_title="Visual Novel Video Generator")

    # Sidebar
    st.sidebar.title("VN Video Gen")
    
    # 0. Global Settings
    debug_mode = st.sidebar.checkbox("Debug Mode", value=False)
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
            cleaned_text, vocab_list = clean_html_content(raw_html)
            
            # 1. Update Cleaned Text
            st.session_state.cleaned_text_preview = cleaned_text
            st.session_state.cleaned_text_preview_widget = cleaned_text
            st.session_state.original_clean_text = cleaned_text
            
            # 2. Update Vocabulary
            st.session_state.vocab_list = vocab_list
            
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
        if st.button("✨ Generate Social Script (Draft)"):
             # Ensure we have the original text safely
             source_text = st.session_state.get('original_clean_text', final_script_text)
             
             with st.spinner("Adapting for Social Media (Gemini)..."):
                 draft = generate_social_script(source_text)
                 if draft:
                     st.session_state.social_script_draft = draft
                     st.session_state.parsed_script = draft # Keep compatibility with Step 2 Video Gen
                     st.success("Social Script Generated!")

        if 'social_script_draft' in st.session_state:
             st.subheader("Edit Social Script (Draft)")
             edited_draft = st.data_editor(st.session_state.social_script_draft, num_rows="dynamic", key='social_draft_editor')
             # Sync back to social_script_draft AND parsed_script (for video generation)
             st.session_state.social_script_draft = edited_draft
             st.session_state.parsed_script = edited_draft

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
    # 4. Generate Video Button
    if st.button("Step 2: Generate Video"):
        if st.session_state.parsed_script:
            generate_video(st.session_state.parsed_script)
            # Force a re-run or just let the user see the success messages. 
            # The session state is updated in place.
        else:
            st.error("Please parse a script first.")

if __name__ == "__main__":
    main()
