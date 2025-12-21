import os
import glob
import logging
import copy
import shutil
from dotenv import load_dotenv
from moviepy import VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips
import sys
from types import ModuleType

# Mock streamlit to avoid errors when importing vocab_functions in CLI
if "streamlit" not in sys.modules:
    mock_st = ModuleType("streamlit")
    mock_st.info = lambda *args, **kwargs: None
    mock_st.error = lambda *args, **kwargs: None
    mock_st.warning = lambda *args, **kwargs: None
    mock_st.success = lambda *args, **kwargs: None
    sys.modules["streamlit"] = mock_st

import video_engine
from vocab_functions import generate_vocab_assets, create_vocab_video_sequence

# Load environment variables
load_dotenv()

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

def main():
    # 1. Setup
    logger.info("Starting Batch Generator...")
    config = video_engine.load_config()
    
    input_dir = "./input_lessons"
    output_dir = "./output"
    
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    
    # 2. File Loop
    files = glob.glob(os.path.join(input_dir, "*.txt"))
    if not files:
        logger.warning(f"No .txt files found in {input_dir}. Please add some lesson files.")
        return

    logger.info(f"Found {len(files)} files to process.")

    for file_path in files:
        filename = os.path.basename(file_path)
        lesson_id = os.path.splitext(filename)[0]
        
        logger.info(f"[{filename}] Processing Lesson ID: {lesson_id}...")
        
        try:
            # 3. Processing (Replicate App Logic)
            
            # Read Content
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_html = f.read()
            
            # Parse
            logger.info(f"[{filename}] Cleaning HTML content...")
            cleaned_text, vocab_list, lesson_title = video_engine.clean_html_content(raw_html)
            
            logger.info(f"[{filename}] Generating scripts (Web & Social)...")
            social_script_dummy, web_script = video_engine.generate_dual_scripts(cleaned_text, config)
            
            if not web_script:
                logger.error(f"[{filename}] Failed to generate scripts. Skipping.")
                continue

            # --- Generate WEB Video ---
            logger.info(f"[{filename}] Generating Web Video...")
            
            # 1. Roster
            web_roster = video_engine.get_active_roster(web_script, config)
            
            # 2. Audio
            web_frames_dir = os.path.join("output", "frames_web")
            web_audio_dir = os.path.join("output", "audio_web")
            
            script_web = copy.deepcopy(web_script)
            script_web = video_engine.generate_audio(
                script_web, config, 
                output_dir=web_audio_dir
            )
            
            # 3. Frames
            video_engine.generate_frames(
                script_web, web_roster, config,
                output_dir=web_frames_dir
            )
            
            # 4. Assemble Story
            web_story_path = video_engine.assemble_video(
                script_web,
                output_dir="output",
                output_filename=f"temp_web_story_{lesson_id}.mp4"
            )
            
            if web_story_path:
                final_web_clips = []
                
                # Title Card
                title_card_path = video_engine.create_title_card(lesson_title, config)
                if os.path.exists(title_card_path):
                    final_web_clips.append(ImageClip(title_card_path).with_duration(3.0))
                
                final_web_clips.append(VideoFileClip(web_story_path))
                
                final_web = concatenate_videoclips(final_web_clips)
                
                web_output_path = os.path.abspath(os.path.join(output_dir, f"{lesson_id}_web.mp4"))
                final_web.write_videofile(web_output_path, codec="libx264", audio_codec="aac", logger=None)
                logger.info(f"[{filename}] Web Video exported: {web_output_path}")
                
            else:
                logger.error(f"[{filename}] Failed to assemble Web Video story.")

            # --- Generate SOCIAL Video (Teaser) ---
            logger.info(f"[{filename}] Generating Social Teaser...")
            
            # Slice: Take first 6 lines
            script_social = copy.deepcopy(web_script[:6]) # Use web_script source to respect dual_script output structure
            
            # Recalculate roster for the slice
            social_roster = video_engine.get_active_roster(script_social, config)
            
            # Generate Audio for Social (Wait, we can reuse if identical, but distinct output dirs is safer)
            # Actually, reusing 'web_script' audio might fail if we slice BEFORE generating audio. 
            # In Web Video step, we generated audio for FULL script.
            # So script_social (which is web_script[:6]) should ALREADY have audio_file keys if we used the populated list.
            # BUT, I used `script_web = copy.deepcopy(web_script)` then generated audio into `script_web`.
            # `web_script` variable itself is still the raw JSON without audio paths.
            # So I need to generate audio for social specifically.
            
            social_audio_dir = os.path.join("output", "audio_social")
            script_social = video_engine.generate_audio(
                script_social, config,
                output_dir=social_audio_dir
            )
            
            # 1. Listening Part (Masked)
            listening_script = copy.deepcopy(script_social)
            for line in listening_script:
                if 'text' in line: line['text'] = "..... ? ....."
                
            video_engine.generate_frames(
                listening_script, social_roster, config,
                output_dir=os.path.join("output", "frames_listening")
            )
            
            listening_video_path = video_engine.assemble_video(
                listening_script,
                output_dir="output",
                output_filename=f"listening_part_{lesson_id}.mp4"
            )
            
            # 2. Reading Part (Normal)
            video_engine.generate_frames(
                script_social, social_roster, config,
                output_dir=os.path.join("output", "frames_reading")
            )
            
            reading_video_path = video_engine.assemble_video(
                script_social,
                output_dir="output",
                output_filename=f"reading_part_{lesson_id}.mp4"
            )
            
            # 3. Assemble Social Video
            final_social_clips = []
            
            # Intro
            if os.path.exists("assets/intro.mp4"):
                intro = VideoFileClip("assets/intro.mp4").resized(new_size=(1080, 1920))
                final_social_clips.append(intro)
                
            # Listening
            if listening_video_path and os.path.exists(listening_video_path):
                final_social_clips.append(VideoFileClip(listening_video_path))
                
            # Separator
            sep_clip = video_engine.create_separator_clip(config, "output")
            if sep_clip: final_social_clips.append(sep_clip)
            
            # Reading
            if reading_video_path and os.path.exists(reading_video_path):
                final_social_clips.append(VideoFileClip(reading_video_path))
                
            # Vocab
            if vocab_list:
                vocab_assets = generate_vocab_assets(vocab_list)
                if vocab_assets:
                    vocab_clip = create_vocab_video_sequence(vocab_assets)
                    if vocab_clip: final_social_clips.append(vocab_clip)
            
            if final_social_clips:
                final_social = concatenate_videoclips(final_social_clips)
                
                # Branding
                if os.path.exists("assets/NoBackground.png"):
                    overlay = ImageClip("assets/NoBackground.png")\
                        .with_duration(final_social.duration)\
                        .with_position(('center', 'bottom'))
                    final_social = CompositeVideoClip([final_social, overlay])
                    
                # Music (Check config/args, defaulting to None for batch as simplistic approach, or check config)
                # App sets config["ENABLE_MUSIC"] based on UI. 
                # Let's assume False for batch unless config has it.
                if config.get("ENABLE_MUSIC"):
                    final_social = video_engine.add_background_music(final_social, "assets")

                # Social Title Overlay
                title_social_path = video_engine.create_social_title_img(lesson_title, config)
                if os.path.exists(title_social_path):
                    title_overlay = ImageClip(title_social_path).with_duration(1.0).with_start(0)
                    final_social = CompositeVideoClip([final_social, title_overlay])
                    
                social_output_path = os.path.abspath(os.path.join(output_dir, f"{lesson_id}.mp4"))
                final_social.write_videofile(social_output_path, codec="libx264", audio_codec="aac", logger=None)
                logger.info(f"[{filename}] Social Video exported: {social_output_path}")
            
            logger.info(f"[{filename}] Done.")
            
        except Exception as e:
            logger.error(f"[{filename}] Error processing file: {e}", exc_info=True)
            
        finally:
            # Cleanup per file
            video_engine.cleanup_workspace()

if __name__ == "__main__":
    main()
