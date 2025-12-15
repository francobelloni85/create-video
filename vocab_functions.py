import logging
import streamlit as st
import os
import asyncio
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy import ImageClip, CompositeVideoClip, ColorClip, concatenate_videoclips, AudioFileClip, AudioClip, concatenate_audioclips

logger = logging.getLogger(__name__)

# --- Vocabulary Video Functions ---

async def _edge_tts_generate(text, voice, output_file):
    """Async helper for edge-tts"""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)

def generate_vocab_assets(vocab_list):
    """
    Phase 1: Asset Factory - Single Summary Slide Strategy
    Generates:
      1. A single summary slide (PNG) with all words (Badges + Text).
      2. A single concatenated audio file (MP3) with all pronunciations + silence.
    Returns a dict with paths to these two assets.
    """
    st.info("Generating Vocabulary Assets (Summary Slide)...")
    logger.info("Generating Vocabulary Assets (Summary Slide)...")
    
    # 1. Init Temp
    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)
    
    # Base Image
    base_image_path = "assets/vocabulary.png"
    if not os.path.exists(base_image_path):
        st.error(f"Base image not found: {base_image_path}")
        logger.error(f"Base image not found: {base_image_path}")
        return None
        
    try:
        img = Image.open(base_image_path).convert("RGBA")
    except Exception as e:
        st.error(f"Failed to load base image: {e}")
        logger.error(f"Failed to load base image: {e}", exc_info=True)
        return None

    draw = ImageDraw.Draw(img)
    
    # Fonts Setup
    font_path_main = "assets/font.ttf"
    if not os.path.exists(font_path_main):
        # Fallback candidates
        candidates = ["arialbd.ttf", "arial.ttf", "SegoeUI.ttf", "Roboto-Bold.ttf"]
        for c in candidates:
             try:
                 ImageFont.truetype(c, 50) 
                 font_path_main = c
                 break
             except:
                 continue
    
    font_size_word = 100 # Slightly smaller than before to ensure fit if 5 items
    font_size_trans = 70
    
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

    # Layout Config
    start_y = 670
    step_y = 180 # Vertical step (USER REQUESTED)
    center_axis_x = 540 # Half of 1080
    center_gap = 20     # Gap from center for both sides
    
    # Badge Config
    badge_color = "#3B82F6" # Blue
    text_color_word = "#FFFFFF"
    text_color_trans = "#000000"
    
    audio_clips = []
    
    # Process Items
    for i, item in enumerate(vocab_list):
        word = item.get('word') or 'Unknown'
        translation = item.get('translation') or 'Unknown'
        
        # --- A. Audio Part ---
        audio_filename = f"vocab_audio_{i}.mp3"
        audio_path = os.path.abspath(os.path.join(temp_dir, audio_filename))
        
        try:
            # Sync wrapper for edge-tts
            asyncio.run(_edge_tts_generate(word, "en-US-ChristopherNeural", audio_path))
            
            # Load as AudioFileClip
            if os.path.exists(audio_path):
                clip = AudioFileClip(audio_path)
                audio_clips.append(clip)
                
                # Add Silence (0.3s)
                # Using a silent list method compatible with moviepy
                silence = AudioClip(lambda t: [0], duration=0.3, fps=44100)
                audio_clips.append(silence)
                
        except Exception as e:
            st.error(f"Audio gen failed for '{word}': {e}")
            logger.error(f"Audio gen failed for '{word}': {e}", exc_info=True)
            
        # --- B. Visual Part ---
        # Calculate Y for this row
        current_y = start_y + (i * step_y)
        
        # 1. Left Side: English Badge
        # We want the Right Edge of the badge to be at (center_axis_x - center_gap)
        
        bbox = draw.textbbox((0, 0), word, font=font_word)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        # Badge Geometry
        padding_total = 100 # 50px each side
        badge_w = text_w + padding_total
        badge_h = text_h + 50 # Vertical padding
        
        # Position: Right aligned to spine
        badge_right_edge = center_axis_x - center_gap
        badge_x1 = badge_right_edge - badge_w
        badge_y1 = current_y
        badge_x2 = badge_right_edge
        badge_y2 = badge_y1 + badge_h
        
        # Draw Rounded Rect
        try:
             draw.rounded_rectangle([badge_x1, badge_y1, badge_x2, badge_y2], radius=40, fill=badge_color)
        except AttributeError:
             draw.rectangle([badge_x1, badge_y1, badge_x2, badge_y2], fill=badge_color)
             
        # Draw English Text (Centered in Badge)
        center_x_badge = badge_x1 + (badge_w // 2)
        center_y_badge = badge_y1 + (badge_h // 2)
        
        try:
            draw.text((center_x_badge, center_y_badge), word, font=font_word, fill=text_color_word, anchor="mm")
        except:
             # Manual fallback
             txt_x = center_x_badge - (text_w // 2)
             txt_y = center_y_badge - (text_h // 2) - 10 
             draw.text((txt_x, txt_y), word, font=font_word, fill=text_color_word)

        # 2. Right Side: Italian Translation
        # Position: Left aligned to spine (X = center_axis_x + center_gap)
        # Vertical: Centered relative to the Badge center
        
        trans_x = center_axis_x + center_gap
        trans_y_center = center_y_badge # Align with badge center
        
        try:
            draw.text((trans_x, trans_y_center), translation, font=font_trans, fill=text_color_trans, anchor="lm") # Left-Middle alignment
        except:
            # Fallback for older Pillow
            bbox_t = draw.textbbox((0, 0), translation, font=font_trans)
            trans_h = bbox_t[3] - bbox_t[1]
            draw.text((trans_x, trans_y_center - (trans_h // 2)), translation, font=font_trans, fill=text_color_trans)

    # Save Summary Image
    summary_path = os.path.abspath(os.path.join(temp_dir, "vocab_summary_slide.png"))
    img.save(summary_path)
    
    # Concatenate Audio
    full_mix_path = os.path.abspath(os.path.join(temp_dir, "vocab_full_mix.mp3"))
    if audio_clips:
        try:
            final_audio = concatenate_audioclips(audio_clips)
            final_audio.write_audiofile(full_mix_path, fps=44100, logger=None)
        except Exception as e:
            st.error(f"Audio concatenation failed: {e}")
            logger.error(f"Audio concatenation failed: {e}", exc_info=True)
            full_mix_path = None
    else:
        full_mix_path = None
        
    return {
        "summary_slide": summary_path,
        "full_audio": full_mix_path
    }

def create_vocab_video_sequence(assets):
    """
    Phase 2: Video Sequence - Single Slide
    """
    st.info("Assembling Vocabulary Summary...")
    
    if not assets or not assets.get("summary_slide") or not assets.get("full_audio"):
        st.error("Missing vocab assets for sequence.")
        logger.error("Missing vocab assets for sequence.")
        return None
        
    img_path = assets["summary_slide"]
    audio_path = assets["full_audio"]
    
    try:
        # Load Audio to get duration
        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration
        
        # Create Image Clip with exact duration
        # Add a small buffer to duration if needed, or exact match
        video_clip = ImageClip(img_path).with_duration(duration)
        video_clip = video_clip.with_audio(audio_clip)
        
        return video_clip
        
    except Exception as e:
        st.error(f"Failed to create vocab sequence: {e}")
        logger.error(f"Failed to create vocab sequence: {e}", exc_info=True)
        return None

