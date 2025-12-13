# 🎬 AI Visual Novel Video Generator (Language Learning)

![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-UI-red.svg)
![Gemini](https://img.shields.io/badge/AI-Gemini%20Flash-orange.svg)
![FFmpeg](https://img.shields.io/badge/Video-FFmpeg-green.svg)

A **Vibe Coding** project: An automated tool that turns raw dialogue text into professional, vertical video lessons for social media (TikTok/Reels). Designed for language schools and creators, it generates a complete "Listening Challenge" flow using AI agents for parsing, audio synthesis, and video assembly.

## ✨ Features

* **🧠 AI Script Parsing:** Uses **Google Gemini** to convert messy text into structured JSON, automatically assigning characters and extracting CEFR levels.
* **🗣️ Multi-Character TTS:** Integrates **Google Cloud Text-to-Speech (Neural2)** to assign distinct, high-quality voices to different characters (e.g., Herbert, Margot, Brian).
* **🎨 Visual Novel Engine:**
    * **Ensemble Layout:** Dynamically positions characters on a stage.
    * **Focus System:** Automatically dims non-speaking characters (50% opacity) and highlights the speaker (100% opacity).
    * **Smart Balloons:** Auto-centering text logic with support for variable content heights.
* **📱 Social Media Optimized:** Generates 9:16 vertical videos (1080x1920) specifically for TikTok/Instagram Reels.
* **🎓 Educational Flow (Challenge Mode):**
    1.  **The Hook:** Intro card with Level & Branding.
    2.  **Blind Listening:** Scene plays with *empty balloons* to test comprehension.
    3.  **The Reveal:** Scene replays with *full subtitles* (Visual Novel style).
    4.  **Vocab Cards:** Flashcards for 5 key words extracted by AI.
* **📦 Dual Output:** Automatically exports both the full "Social Video" and a clean "Dialogue Only" version for website usage.

## 🛠️ Tech Stack

* **Core:** Python 3.12
* **UI:** Streamlit
* **LLM:** Google Gemini 2.0 Flash Exp
* **Audio:** Google Cloud TTS
* **Image Processing:** Pillow (PIL)
* **Video Assembly:** FFmpeg & ffmpeg-python

## 🚀 Installation

1.  **Clone the repository**
    ```bash
    git clone https://github.com/francobelloni85/create-video.git
    cd create-video
    ```

2.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

3.  **FFmpeg Setup**
    Ensure FFmpeg is installed and added to your system PATH.
    * *Windows:* Download from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/), extract, and add `bin` folder to PATH.
    * *Mac:* `brew install ffmpeg`

4.  **Environment Variables**
    Create a `.env` file in the root directory and add your API keys:
    ```env
    GEMINI_API_KEY=your_gemini_api_key_here
    GOOGLE_APPLICATION_CREDENTIALS=path/to/your/google_cloud_credentials.json
    ```

## ⚙️ Configuration

The project is fully data-driven via `config.json`. You can customize characters, voices, and colors without changing code.

```json
{
  "settings": {
    "background_color": "#FFFFFF",
    "website_url": "https://www.baobab.school"
  },
  "characters": {
    "Herbert Walker": {
      "image": "assets/herbert.png",
      "voice_params": { "name": "en-US-Neural2-D", "ssml_gender": "MALE" }
    }
    // ... add more characters here
  }
}   
```

## 📖 Usage

Run the application:

```bash
streamlit run app.py
```

1. Paste a raw dialogue (e.g., "Dad says I'm hungry") into the text area.

2. Click "Parse Script" to let Gemini structure the data.

3. Review the table and click "Generate Video".

4. Find your videos in the output/ folder!

## 📂 Project Structure

```json
├── app.py                # Main logic (UI, Audio, Visuals, Video) 
├── config.json           # Character and scene settings
├── requirements.txt      # Python dependencies
├── .env                  # API Keys (Not included in repo)
├── assets/               # Images (balloon.png, characters, font)
└── output/               # Generated media files
```

## 🤖 About "Vibe Coding"

This project was built using a Vibe Coding methodology: rapidly iterating from idea to MVP by leveraging an AI Pair Programmer to handle boilerplate, library integration, and error handling, allowing the developer to focus on high-level logic, creative direction, and educational value.

## 📄 License

This project is open-source for educational purposes.