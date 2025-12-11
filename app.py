import streamlit as st
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Load configuration
import google.generativeai as genai

# Load configuration
def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        st.error("config.json not found.")
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
        return []

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(config['gemini_model'])

        system_prompt = """
        You are an expert script parser for a video generation engine.
        Your task is to convert raw narrative text into a structured JSON list.
    
        **Output Format:**
        A list of objects: `[{"speaker": "Exact Character Name", "text": "Cleaned Dialogue content"}]`
    
        **Character Mapping Rules (STRICT):**
        - If the text mentions "Herbert", "Mr. Walker", or "Dad" -> Map speaker to: "Herbert Walker"
        - If the text mentions "Margot", "Mrs. Walker", or "Mom" -> Map speaker to: "Margot Walker"
        - If the text mentions "Brian" -> Map speaker to: "Brian Walker"
        - If the text mentions "Laura" -> Map speaker to: "Laura Walker"
        - If the text mentions "Molly" -> Map speaker to: "Molly Walker"
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
        {"speaker": "Brian Walker", "text": "I am hungry."},
        {"speaker": "Narrator", "text": "Molly laughs."},
        {"speaker": "Molly Walker", "text": "Me too!"}
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
        return parsed_data
        
    except Exception as e:
        st.error(f"Error parsing script: {e}")
        return []

# --- Helper Functions ---

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
            # Robustness check: try to find close matches or just accept if mapped correctly
            if speaker in valid_characters:
                roster.add(speaker)
            else:
                # Optional: Handle unknown characters or fuzzy match
                # For now, just warn and strict filter
                st.warning(f"Warning: Unknown character '{speaker}' detected.")
    
    return list(roster)

def generate_video(parsed_script):
    """
    Step 2: Generate Video (Modules B, C, D)
    Main orchestration loop.
    """
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    # 1. Active Roster
    status_text.text("Determining active roster...")
    roster = get_active_roster(parsed_script)
    st.write(f"Active Characters: {roster}")
    progress_bar.progress(10)
    
    # Placeholder for further steps
    # 2. Audio Generation
    # 3. Visuals
    # 4. Assembly
    
    st.success("Roster determined. (Waiting for further backend logic implementation)")

# --- Streamlit UI ---

def main():
    st.set_page_config(page_title="Visual Novel Video Generator")

    # Sidebar
    st.sidebar.title("VN Video Gen")

    # Main Area
    st.title("Visual Novel Video Generator")

    # 1. Raw Dialogue Input
    raw_script = st.text_area("Raw Dialogue Input", height=300, placeholder="Paste your messy script here...")

    # 2. Parse Script Button
    if st.button("Step 1: Parse Script"):
        with st.spinner("Parsing script with Gemini..."):
            parsed_result = parse_script(raw_script)
            if parsed_result:
                st.session_state.parsed_script = parsed_result
                st.success("Script parsed successfully!")
            
    
    # Placeholder for session state to store parsed script
    if 'parsed_script' not in st.session_state:
        # Default empty state or instruction
        st.session_state.parsed_script = []

    # 3. Review & Edit
    st.subheader("Review & Edit")
    if st.session_state.parsed_script:
        edited_script = st.data_editor(st.session_state.parsed_script, num_rows="dynamic", key='parsed_editor')
        # Update session state with edits (though data_editor does this automatically with key, explicit sync is good if needed elsewhere)
        st.session_state.parsed_script = edited_script
    else:
        st.info("No script parsed yet. Enter text above and click 'Parse Script'.")

    # 4. Generate Video Button
    if st.button("Step 2: Generate Video"):
        st.info("Generating video... (Logic not implemented yet)")
        # stub logic
        pass

if __name__ == "__main__":
    main()
