import streamlit as st
import os
import asyncio
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy import ImageClip, CompositeVideoClip, ColorClip, concatenate_videoclips, AudioFileClip

# --- Vocabulary Video Functions ---

async def _edge_tts_generate(text, voice, output_file):
    """Async helper for edge-tts"""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)

def generate_vocab_assets(vocab_list):
    """
    Phase 1: Asset Factory
    Generates audio (MP3) and image cards (PNG) for the vocabulary list.
    """
    st.info("Generating Vocabulary Assets...")
    
    # 1. Clean/Init Temp Folder
    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)
    
    # Clean existing temp files? Maybe risky if parallel. 
    # Let's just overwrite by index.
    
    generated_assets = []
    
    # 2. Iteration
    progress_bar = st.progress(0)
    total = len(vocab_list)
    
    font_path_main = "assets/font.ttf"
    if not os.path.exists(font_path_main):
        # Fallback to system fonts or provided arial
        # Try a list of common bold fonts
        candidates = ["arialbd.ttf", "arial.ttf", "SegoeUI.ttf", "Roboto-Bold.ttf"]
        found = False
        for c in candidates:
             try:
                 ImageFont.truetype(c, 50) # value check
                 font_path_main = c
                 found = True
                 break
             except:
                 continue
        if not found:
            font_path_main = None # Use default fallback

    for i, item in enumerate(vocab_list):
        word = item.get('word') or 'Unknown'
        translation = item.get('translation') or 'Unknown'
        
        # --- A. Audio Generation (EdgeTTS) ---
        audio_filename = f"vocab_audio_{i}.mp3"
        audio_path = os.path.join(temp_dir, audio_filename)
        audio_path = os.path.abspath(audio_path)
        
        try:
            # Run async function in sync context
            asyncio.run(_edge_tts_generate(word, "en-US-ChristopherNeural", audio_path))
        except Exception as e:
            st.error(f"EdgeTTS failed for '{word}': {e}")
            # Fallback? Create silent mp3? Or just skip?
            # Create a 1s silent audio just in case to not break pipeline
            # For now, let's hope it works or user sees error.
        
        # --- B. Image Card Generation ---
        card_filename = f"vocab_card_{i}.png"
        card_path = os.path.join(temp_dir, card_filename)
        card_path = os.path.abspath(card_path)
        
        try:
            # Canvas 1080x1920
            img = Image.new('RGB', (1080, 1920), color='#FFFFFF')
            draw = ImageDraw.Draw(img)
            
            # Fonts
            # Large Bold Black for Word (Top)
            # Slightly Smaller Dark Grey for Translation (Bottom)
            
            font_size_word = 120
            font_size_trans = 100
            
            if font_path_main:
                try:
                    font_word = ImageFont.truetype(font_path_main, font_size_word)
                    font_trans = ImageFont.truetype(font_path_main, font_size_trans)
                except:
                    font_word = ImageFont.load_default()
                    font_trans = ImageFont.load_default()
            else:
                 font_word = ImageFont.load_default()
                 font_trans = ImageFont.load_default()

            # Colors
            color_word = "#000000"
            color_trans = "#333333"
            
            # Position: Word ~ Y=30% (576px), Trans ~ Y=75% (1440px)
            # Center Horizontally
            
            # Helper to draw centered
            def draw_centered(text, y_pos, font, fill):
                bbox = draw.textbbox((0, 0), text, font=font)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                x = (1080 - w) // 2
                draw.text((x, y_pos - h//2), text, font=font, fill=fill)
            
            draw_centered(word, 576, font_word, color_word)
            draw_centered(translation, 1440, font_trans, color_trans)
            
            img.save(card_path)
            
            generated_assets.append({
                "index": i,
                "word": word,
                "audio": audio_path,
                "image": card_path
            })
            
        except Exception as e:
            st.error(f"Image gen failed for '{word}': {e}")
            
        progress_bar.progress((i + 1) / total)
        
    return generated_assets

def create_vocab_video_sequence(assets):
    """
    Phase 2: Video Sequence Assembly
    Uses MoviePy to create the closing segment.
    """
    st.info("Assembling Vocabulary Sequence...")
    
    vocab_clips = []
    
    # 1. Intro Stinger
    intro_path = "assets/vocabulary.png"
    if os.path.exists(intro_path):
        try:
            intro_clip = ImageClip(intro_path).with_duration(1.0)
            vocab_clips.append(intro_clip)
        except Exception as e:
            st.warning(f"Could not load intro stinger: {e}")
    else:
        st.warning(f"Intro stinger not found at {intro_path}")

    # 2. Cards Loop
    for item in assets:
        img_path = item['image']
        audio_path = item['audio']
        
        if not os.path.exists(img_path) or not os.path.exists(audio_path):
            continue
            
        try:
            # Base Clip (Image) - 3.0s
            base_clip = ImageClip(img_path).with_duration(3.0)
            
            # Audio
            audio_clip = AudioFileClip(audio_path)
            # Start audio at 0? Or delayed?
            # "Pronouncing only the English word". Usually short.
            # Let's set it to start at 0.
            base_clip = base_clip.with_audio(audio_clip)
            
            # Reveal Mask (ColorClip)
            # White box covering bottom 50%
            # Duration: 0.0s to 1.5s
            # Geometry: 1080x960, pos=(0, 960)
            
            mask_clip = ColorClip(size=(1080, 960), color=(255, 255, 255))
            mask_clip = mask_clip.with_position((0, 960))
            mask_clip = mask_clip.with_start(0).with_duration(1.5)
            
            # Composite
            final_card_clip = CompositeVideoClip([base_clip, mask_clip], size=(1080, 1920))
            final_card_clip = final_card_clip.with_duration(3.0) # Enforce 3s
            
            vocab_clips.append(final_card_clip)
            
        except Exception as e:
            st.error(f"Failed to create clip for item {item['index']}: {e}")

    # 3. Concatenate
    if vocab_clips:
        try:
            final_vocab_sequence = concatenate_videoclips(vocab_clips, method="compose")
            return final_vocab_sequence
        except Exception as e:
            st.error(f"Error concatenating vocab clips: {e}")
            return None
    else:
        return None

