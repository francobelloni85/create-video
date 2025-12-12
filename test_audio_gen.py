import os
from google.cloud import texttospeech
from dotenv import load_dotenv

load_dotenv()

def test_tts():
    print("Testing TTS initialization...")
    creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    print(f"GOOGLE_APPLICATION_CREDENTIALS: {creds}")
    
    if not os.path.exists(creds):
        print(f"Error: Credentials file not found at {creds}")
        return

    try:
        client = texttospeech.TextToSpeechClient()
        
        synthesis_input = texttospeech.SynthesisInput(text="Hello, testing audio generation.")
        
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name="en-US-Journey-D",
            ssml_gender=texttospeech.SsmlVoiceGender.MALE
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        print("Sending request to Google TTS...")
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        filename = "test_output.mp3"
        with open(filename, "wb") as out:
            out.write(response.audio_content)
            
        print(f"Success! Audio content written to {filename}")
        
    except Exception as e:
        print(f"TTS Test Failed: {e}")

if __name__ == "__main__":
    test_tts()
