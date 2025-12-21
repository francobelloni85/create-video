import streamlit as st
import os
import time
import logging
import copy
import shutil
from moviepy import VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips

# Import core engine and vocab functions
import video_engine
from vocab_functions import generate_vocab_assets, create_vocab_video_sequence

def main():
    st.set_page_config(page_title="Visual Novel Video Generator")

    # --- Sidebar & Setup ---
    st.sidebar.title("VN Video Gen")
    
    # Load Config via Engine
    config = video_engine.load_config()
    
    # Global Settings
    debug_mode = st.sidebar.checkbox("Debug Mode", value=config.get('debug_mode', False))
    config['debug_mode'] = debug_mode
    video_engine.setup_logging(debug_mode)
    
    if debug_mode:
        st.sidebar.warning("Debug Mode Enabled: detailed logs in app.log")

    # Dev Tools
    st.sidebar.markdown("---")
    st.sidebar.subheader("Dev Tools")
    if st.sidebar.button("Test Audio Generation"):
        with st.spinner("Testing Audio..."):
            # Test with Narrator
            path_n, dur_n = video_engine.generate_single_audio("This is a test of the narrator voice.", "Narrator", 999, config)
            if path_n:
                st.sidebar.audio(path_n)
                st.sidebar.success(f"Narrator: {dur_n:.2f}s")
    
    # --- Main UI ---
    st.title("Visual Novel Video Generator")
    
    # Helper for status updates
    status_text = st.empty()
    main_progress = st.progress(0)
    
    def update_status_callback(progress, text=None):
        if text:
            # Simple ETR calculation could go here if persistent state was tracked, 
            # for now just update text/bar to keep it clean.
            status_text.text(text)
        main_progress.progress(progress)

    # 1. HTML Input
    raw_html = st.text_area("Paste Lesson HTML", height=300, placeholder="Paste the full lesson HTML code here...")

    # Button: Clean
    if st.button("Clean & Preview Text"):
        with st.spinner("Cleaning HTML..."):
            cleaned_text, vocab_list, lesson_title = video_engine.clean_html_content(raw_html)
            
            # Update Session State
            st.session_state.cleaned_text_preview = cleaned_text
            st.session_state.cleaned_text_preview_widget = cleaned_text
            st.session_state.original_clean_text = cleaned_text
            st.session_state.vocab_list = vocab_list
            st.session_state.lesson_title = lesson_title
            
            st.write(f"**Lesson Title:** {lesson_title}")
            if vocab_list:
                st.success(f"Extracted {len(vocab_list)} extracted vocabulary items.")

    # 2. Preview & Generate Script
    if 'cleaned_text_preview' in st.session_state and st.session_state.cleaned_text_preview:
        
        # Vocab Editor
        if 'vocab_list' in st.session_state and st.session_state.vocab_list:
            st.subheader("Extracted Vocabulary")
            edited_vocab = st.data_editor(
                st.session_state.vocab_list,
                num_rows="dynamic",
                key="vocab_editor"
            )
            st.session_state.vocab_list = edited_vocab
            st.write("---")
        
        st.subheader("Cleaned English Text")
        final_script_text = st.text_area(
            "Verify & Edit Text", 
            key='cleaned_text_preview_widget', 
            value=st.session_state.cleaned_text_preview,
            height=200
        )
        
        # Generate Scripts Button
        st.write("---")
        if st.button("Step 2: Generate Web Script"):
            source_text = st.session_state.get('original_clean_text', final_script_text)
            
            with st.spinner("Generating Web Script..."):
                social, web = video_engine.generate_dual_scripts(source_text, config)
                
                if web:
                    st.session_state.script_web = web
                    # Auto-derive Social Script (First 6 lines)
                    st.session_state.script_social = web[:6]
                    st.success("Web Script & Social Teaser Generated!")
                else:
                    st.error("Failed to generate scripts.")

        # Script Editors
        if 'script_web' in st.session_state:
            st.subheader("Script Editor (Full Story)")
            edited_web = st.data_editor(
                st.session_state.script_web, 
                num_rows="dynamic", 
                key='web_editor',
                use_container_width=True
            )
            st.session_state.script_web = edited_web
            
            # Sync Social Script
            st.session_state.script_social = edited_web[:6]

    # 3. Create Video
    if 'script_web' in st.session_state:
        st.write("---")
        st.header("Step 3: Create Video")
        
        use_music = st.checkbox("Add Background Music 🎵", value=False)
        config["ENABLE_MUSIC"] = use_music

        if st.button("Generate Video"):
            # --- START GENERATION ORCHESTRATION ---
            

            
            # Get Codec Settings
            video_codec = config.get('settings', {}).get('video_codec', 'libx264')
            write_kwargs = {"codec": video_codec, "audio_codec": "aac", "logger": None}
            
            # Safety Check for Hardware Encoders
            if video_codec != "libx264":
                write_kwargs["preset"] = "p4"

            # --- A. SOCIAL VIDEO (Complex Sequence) ---
            st.subheader("Generating Social Video...")
            social_script = copy.deepcopy(st.session_state.script_social)
            
            try:
                # 1. Roster
                update_status_callback(0.05, "Social: Determining Roster...")
                roster = video_engine.get_active_roster(social_script, config)
                
                # 2. Audio
                update_status_callback(0.10, "Social: Generating Audio...")
                # Pass lambda directly to capture progress within the sub-range 0.1->0.2
                social_script = video_engine.generate_audio(
                    social_script, 
                    config, 
                    output_dir="output", # Shared output for audio? Or distinct? Engine uses "output" default.
                    progress_callback=lambda p: update_status_callback(0.10 + (p * 0.1))
                )
                
                # 3. Listening Part (Masked)
                update_status_callback(0.20, "Social: Generating Listening Part...")
                listening_script = copy.deepcopy(social_script)
                for line in listening_script:
                    if 'text' in line: line['text'] = "..... ? ....."
                
                video_engine.generate_frames(
                    listening_script, roster, config, 
                    output_dir="output/frames_listening",
                    progress_callback=lambda p: update_status_callback(0.20 + (p * 0.1))
                )
                
                listening_video_path = video_engine.assemble_video(
                    listening_script, 
                    output_dir="output", 
                    output_filename="listening_part.mp4",
                    config=config
                )
                
                # 4. Reading Part (Normal)
                update_status_callback(0.35, "Social: Generating Reading Part...")
                video_engine.generate_frames(
                    social_script, roster, config,
                    output_dir="output/frames_reading",
                    progress_callback=lambda p: update_status_callback(0.35 + (p * 0.1))
                )
                
                reading_video_path = video_engine.assemble_video(
                    social_script,
                    output_dir="output",
                    output_filename="reading_part.mp4",
                    config=config
                )
                
                # 5. Final Composition (APP Logic)
                update_status_callback(0.50, "Social: Assembling Final Clip...")
                
                final_clips = []
                
                # Intro
                if os.path.exists("assets/intro.mp4"):
                    intro = VideoFileClip("assets/intro.mp4").resized(new_size=(1080, 1920))
                    if intro.duration > 1:
                        intro = intro.subclipped(0, intro.duration - 0.3)
                    final_clips.append(intro)
                
                # Listening
                if listening_video_path and os.path.exists(listening_video_path):
                    final_clips.append(VideoFileClip(listening_video_path))
                
                # Separator
                sep_clip = video_engine.create_separator_clip(config, "output")
                if sep_clip: final_clips.append(sep_clip)
                
                # Reading
                if reading_video_path and os.path.exists(reading_video_path):
                    final_clips.append(VideoFileClip(reading_video_path))
                
                # Vocab (Conditional)
                if st.session_state.get('vocab_list'):
                    vocab_assets = generate_vocab_assets(st.session_state.vocab_list)
                    if vocab_assets:
                        vocab_clip = create_vocab_video_sequence(vocab_assets)
                        if vocab_clip: final_clips.append(vocab_clip)
                
                # Concatenate
                if final_clips:
                    final_combined = concatenate_videoclips(final_clips)
                    
                    # Branding
                    if os.path.exists("assets/NoBackground.png"):
                        overlay = ImageClip("assets/NoBackground.png")\
                            .with_duration(final_combined.duration)\
                            .with_position(('center', 'bottom'))
                        final_combined = CompositeVideoClip([final_combined, overlay])
                    
                    # Music
                    if config.get("ENABLE_MUSIC"):
                        final_combined = video_engine.add_background_music(final_combined, "assets")
                    
                    # Social Title Overlay (Text Flash)
                    title_social_path = video_engine.create_social_title_img(st.session_state.lesson_title, config)
                    if os.path.exists(title_social_path):
                        title_overlay = ImageClip(title_social_path).with_duration(1.0).with_start(0)
                        final_combined = CompositeVideoClip([final_combined, title_overlay])
                        
                    # Export
                    update_status_callback(0.55, "Social: Exporting MP4...")
                    social_output_path = os.path.abspath(os.path.join("output", "final_video_complete.mp4"))

                    final_combined.write_videofile(social_output_path, **write_kwargs)
                    
                    st.success("Social Video Generated!")
                    st.video(social_output_path)
                else:
                    st.error("No clips to assemble for Social Video.")

            except Exception as e:
                st.error(f"Social Video Failed: {e}")
                logging.error("Social Video Failed", exc_info=True)


            # --- B. WEB VIDEO (Simple Sequence) ---
            st.subheader("Generating Web Video...")
            web_script = copy.deepcopy(st.session_state.script_web)
            
            try:
                # 1. Roster
                web_roster = video_engine.get_active_roster(web_script, config)
                
                # 2. Audio
                update_status_callback(0.65, "Web: Generating Audio...")
                web_script = video_engine.generate_audio(
                    web_script, config,
                    output_dir="output/audio_web",
                    progress_callback=lambda p: update_status_callback(0.65 + (p * 0.1))
                )
                
                # 3. Frames
                update_status_callback(0.75, "Web: Generating Frames...")
                video_engine.generate_frames(
                    web_script, web_roster, config,
                    output_dir="output/frames_web",
                    progress_callback=lambda p: update_status_callback(0.75 + (p * 0.1))
                )
                
                # 4. Assemble Story
                story_path = video_engine.assemble_video(
                    web_script,
                    output_dir="output",
                    output_filename="temp_web_story.mp4",
                    config=config
                )
                
                if story_path:
                    # 5. Title Card & Composition
                    final_web_clips = []
                    
                    title_card_path = video_engine.create_title_card(st.session_state.lesson_title, config)
                    if os.path.exists(title_card_path):
                        final_web_clips.append(ImageClip(title_card_path).with_duration(3.0))
                    
                    final_web_clips.append(VideoFileClip(story_path))
                    
                    final_web = concatenate_videoclips(final_web_clips)
                    
                    # Export
                    update_status_callback(0.95, "Web: Exporting MP4...")
                    web_output_path = os.path.abspath(os.path.join("output", "Web_Video.mp4"))

                    final_web.write_videofile(web_output_path, **write_kwargs)
                    
                    st.success("Web Video Generated!")
                    st.video(web_output_path)
                    
            except Exception as e:
                st.error(f"Web Video Failed: {e}")
                logging.error("Web Video Failed", exc_info=True)
                
            update_status_callback(1.0, "All Done!")
            
            # Cleanup
            if not debug_mode:
                video_engine.cleanup_workspace()
                st.toast("Temporary files cleaned.")

if __name__ == "__main__":
    main()
