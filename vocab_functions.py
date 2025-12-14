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
            # English Word: Bigger
            # Translation: Smaller
            font_size_word = 130
            font_size_trans = 90
            
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
            primary_color = "#4F46E5" # Indigo/Blue
            text_color_word = "#FFFFFF" # White
            text_color_trans = "#222222" # Dark Grey/Black
            
            # --- Layout Calculations ---
            # Word Center Y = 42% of 1920 ~= 806
            # Trans Center Y = 58% of 1920 ~= 1114
            
            y_center_word = 806
            y_center_trans = 1114
            
            # 1. Draw English Word (Badge Style)
            # Calculate text size
            bbox_word = draw.textbbox((0, 0), word, font=font_word)
            w_word = bbox_word[2] - bbox_word[0]
            h_word = bbox_word[3] - bbox_word[1]
            
            # Badge dimensions with padding
            pad_x = 60
            pad_y = 40
            badge_w = w_word + (pad_x * 2)
            badge_h = h_word + (pad_y * 2)
            
            badge_x1 = (1080 - badge_w) // 2
            badge_y1 = y_center_word - (badge_h // 2)
            badge_x2 = badge_x1 + badge_w
            badge_y2 = badge_y1 + badge_h
            
            # Draw Badge (Rounded Rectangle)
            try:
                draw.rounded_rectangle([badge_x1, badge_y1, badge_x2, badge_y2], radius=40, fill=primary_color)
            except AttributeError:
                # Fallback for older Pillow versions
                draw.rectangle([badge_x1, badge_y1, badge_x2, badge_y2], fill=primary_color)
            
            # Draw Word Text (Centered in Badge)
            # Note: aligning text perfectly can be tricky with ascenders/descenders. 
            # Using basic centering logic here.
            text_x_word = (1080 - w_word) // 2
            text_y_word = y_center_word - (h_word // 2)
            draw.text((text_x_word, text_y_word - 10), word, font=font_word, fill=text_color_word) 
            # -10 fix for visual centering often needed with PIL fonts

            # 2. Draw Translation (Simple Text)
            bbox_trans = draw.textbbox((0, 0), translation, font=font_trans)
            w_trans = bbox_trans[2] - bbox_trans[0]
            h_trans = bbox_trans[3] - bbox_trans[1]
            
            text_x_trans = (1080 - w_trans) // 2
            text_y_trans = y_center_trans - (h_trans // 2)
            
            draw.text((text_x_trans, text_y_trans), translation, font=font_trans, fill=text_color_trans)
            
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
            intro_clip = ImageClip(intro_path).with_duration(2.0)
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
            # Base Clip (Image) - 2.5s
            base_clip = ImageClip(img_path).with_duration(2.5)
            
            # Audio
            audio_clip = AudioFileClip(audio_path)
            # Start audio at 0? Or delayed?
            # "Pronouncing only the English word". Usually short.
            # Let's set it to start at 0.
            base_clip = base_clip.with_audio(audio_clip)
            
            # Reveal Mask (ColorClip)
            # White box covering bottom 50%
            # Duration: 0.0s to 1.2s (Reveal at 1.2s)
            # Geometry: 1080x960, pos=(0, 960)
            
            mask_clip = ColorClip(size=(1080, 960), color=(255, 255, 255))
            mask_clip = mask_clip.with_position((0, 960))
            mask_clip = mask_clip.with_start(0).with_duration(1.2)
            
            # Composite
            final_card_clip = CompositeVideoClip([base_clip, mask_clip], size=(1080, 1920))
            final_card_clip = final_card_clip.with_duration(2.5) # Enforce 2.5s
            
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

