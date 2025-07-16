"""
Speech processing integration combining STT, TTS, and audio handling
"""
import sys
import os
import tempfile
import base64
import requests
from typing import Optional, Dict, Any
import numpy as np
import soundfile as sf

# Add voice directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'voice'))

try:
    from voice.Dia_TTS import RealTimeVoiceAI
except ImportError as e:
    print(f"Warning: Could not import Dia_TTS: {e}")
    RealTimeVoiceAI = None

from groq import Groq
from config.credentials import credential_manager
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

class SpeechProcessor:
    """Handles speech-to-text and text-to-speech processing"""
    
    def __init__(self, voice: str = "af_sarah"):
        """Initialize speech processor with lazy TTS loading"""
        
        # Initialize Groq for STT
        self.groq_client = Groq(api_key=credential_manager.get_groq_api_key())
        
        # FIXED: Lazy initialization for Dia_TTS
        self._voice_ai = None
        self.voice = voice
        self._tts_initialized = False
        
        logger.info("SpeechProcessor initialized with lazy TTS loading")
    
    def _get_voice_ai(self) -> Optional[object]:
        """Lazy initialization of voice AI (only when needed)"""
        if self._voice_ai is None and not self._tts_initialized:
            self._tts_initialized = True  # Mark as attempted
            
            if RealTimeVoiceAI:
                try:
                    logger.info(f"Initializing Dia_TTS with {self.voice} voice...")
                    self._voice_ai = RealTimeVoiceAI(
                        groq_api_key=credential_manager.get_groq_api_key(),
                        voice=self.voice
                    )
                    logger.info(f"Dia_TTS initialized successfully with {self.voice} voice")
                except Exception as e:
                    logger.error(f"Failed to initialize Dia_TTS: {e}")
                    self._voice_ai = None
            else:
                logger.warning("Dia_TTS not available - TTS features disabled")
        
        return self._voice_ai
    
    @property
    def voice_ai(self):
        """Property to access voice AI with lazy loading"""
        return self._get_voice_ai()
    
    def transcribe_audio_url(self, audio_url: str, auth_token: Optional[str] = None) -> str:
        """Transcribe audio from URL (e.g., Twilio recording)"""
        try:
            # Download audio file
            headers = {}
            if auth_token:
                headers['Authorization'] = f'Basic {auth_token}'
            
            response = requests.get(audio_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                tmp_file.write(response.content)
                temp_path = tmp_file.name
            
            # Transcribe using Groq Whisper
            transcription = self._transcribe_audio_file(temp_path)
            
            # Clean up
            os.unlink(temp_path)
            
            return transcription
            
        except Exception as e:
            logger.error(f"Failed to transcribe audio from URL {audio_url}: {e}")
            return ""
    
    def transcribe_audio_file(self, file_path: str) -> str:
        """Transcribe audio from local file"""
        return self._transcribe_audio_file(file_path)
    
    def _transcribe_audio_file(self, file_path: str) -> str:
        """Internal method to transcribe audio file using Groq"""
        try:
            logger.info(f"Transcribing audio file: {file_path}")
            
            with open(file_path, "rb") as audio_file:
                transcription = self.groq_client.audio.transcriptions.create(
                    file=(os.path.basename(file_path), audio_file.read()),
                    model="whisper-large-v3-turbo",
                    response_format="verbose_json",
                    language="en"
                )
            
            text = transcription.text.strip()
            confidence = getattr(transcription, 'confidence', 1.0)
            
            logger.info(f"Transcription completed: '{text}' (confidence: {confidence})")
            return text
            
        except Exception as e:
            logger.error(f"Transcription failed for {file_path}: {e}")
            return ""
    
    def generate_speech_audio(self, text: str) -> Optional[np.ndarray]:
        """Generate speech audio using Dia_TTS"""
        voice_ai = self.voice_ai  # This triggers lazy loading
        
        if not voice_ai:
            logger.error("Dia_TTS not available for speech generation")
            return None
        
        try:
            logger.info(f"Generating speech for: '{text[:50]}...'")
            
            # Use Dia_TTS to generate audio
            audio_array = self._generate_audio_with_dia_tts(text)
            
            if audio_array is not None:
                logger.info(f"Speech generation successful, audio length: {len(audio_array)} samples")
                return audio_array
            else:
                logger.warning("Speech generation returned no audio")
                return None
                
        except Exception as e:
            logger.error(f"Speech generation failed: {e}")
            return None
    
    def _generate_audio_with_dia_tts(self, text: str) -> Optional[np.ndarray]:
        """Generate audio using Dia_TTS system"""
        try:
            voice_ai = self.voice_ai
            if not voice_ai:
                return None
            
            # Check if we have cached audio
            cached_audio = voice_ai.get_cached_response(text)
            if cached_audio is not None:
                return cached_audio
            
            # Generate new audio using Kokoro
            generator = voice_ai.kokoro(text, voice=self.voice)
            
            audio_chunks = []
            for i, (gs, ps, audio) in enumerate(generator):
                audio_chunks.append(audio)
                # Limit chunks to avoid hanging
                if i > 10:
                    break
            
            if audio_chunks:
                full_audio = np.concatenate(audio_chunks)
                
                # Cache the audio for future use
                if len(text) < 100:
                    voice_ai.tts_cache[text] = full_audio
                
                return full_audio
            
            return None
            
        except Exception as e:
            logger.error(f"Dia_TTS audio generation failed: {e}")
            return None
    
    def save_audio_to_file(self, audio_array: np.ndarray, file_path: str) -> bool:
        """Save audio array to file"""
        try:
            sf.write(file_path, audio_array, settings.TTS_SAMPLE_RATE)
            logger.info(f"Audio saved to: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save audio to {file_path}: {e}")
            return False
    
    def audio_to_base64(self, audio_array: np.ndarray) -> str:
        """Convert audio array to base64 string"""
        try:
            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                sf.write(tmp_file.name, audio_array, settings.TTS_SAMPLE_RATE)
                
                # Read as base64
                with open(tmp_file.name, 'rb') as audio_file:
                    audio_b64 = base64.b64encode(audio_file.read()).decode()
                
                os.unlink(tmp_file.name)
                return audio_b64
                
        except Exception as e:
            logger.error(f"Audio to base64 conversion failed: {e}")
            return ""
    
    def convert_audio_format(self, input_path: str, output_path: str, target_rate: int = 8000) -> bool:
        """Convert audio file format/sample rate for Twilio compatibility"""
        try:
            # Read audio file
            data, sample_rate = sf.read(input_path)
            
            # Resample if needed
            if sample_rate != target_rate:
                import librosa
                data = librosa.resample(data, orig_sr=sample_rate, target_sr=target_rate)
            
            # Ensure mono
            if len(data.shape) > 1:
                data = np.mean(data, axis=1)
            
            # Save converted audio
            sf.write(output_path, data, target_rate)
            
            logger.info(f"Audio converted: {input_path} -> {output_path} ({target_rate} Hz)")
            return True
            
        except Exception as e:
            logger.error(f"Audio conversion failed: {e}")
            return False
    
    def validate_audio_file(self, file_path: str) -> Dict[str, Any]:
        """Validate audio file and return metadata"""
        try:
            data, sample_rate = sf.read(file_path)
            
            return {
                'valid': True,
                'duration': len(data) / sample_rate,
                'sample_rate': sample_rate,
                'channels': 1 if len(data.shape) == 1 else data.shape[1],
                'samples': len(data),
                'file_size': os.path.getsize(file_path)
            }
            
        except Exception as e:
            logger.error(f"Audio validation failed for {file_path}: {e}")
            return {'valid': False, 'error': str(e)}
    
    def test_speech_processing(self) -> Dict[str, bool]:
        """Test speech processing capabilities"""
        results = {
            'stt_available': False,
            'tts_available': False,
            'dia_tts_available': False
        }
        
        try:
            # Test STT (Groq)
            test_audio = np.random.normal(0, 0.1, 16000)  # 1 second of noise
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                sf.write(tmp_file.name, test_audio, 16000)
                transcription = self._transcribe_audio_file(tmp_file.name)
                results['stt_available'] = True
                os.unlink(tmp_file.name)
                
        except Exception as e:
            logger.error(f"STT test failed: {e}")
        
        try:
            # Test TTS (Dia_TTS) - triggers lazy loading
            voice_ai = self.voice_ai
            if voice_ai:
                test_audio = self.generate_speech_audio("Test")
                results['tts_available'] = test_audio is not None
                results['dia_tts_available'] = True
                
        except Exception as e:
            logger.error(f"TTS test failed: {e}")
        
        logger.info(f"Speech processing test results: {results}")
        return results
    
    def get_available_voices(self) -> list:
        """Get list of available TTS voices"""
        voice_ai = self.voice_ai
        if voice_ai and hasattr(voice_ai, 'available_voices'):
            return voice_ai.available_voices
        return ['af_sarah', 'af_bella', 'af_heart', 'am_adam', 'am_michael']
    
    def switch_voice(self, new_voice: str) -> bool:
        """Switch TTS voice"""
        voice_ai = self.voice_ai
        if not voice_ai:
            return False
        
        try:
            # Test the new voice
            test_generator = voice_ai.kokoro("Voice test", voice=new_voice)
            test_chunk = next(test_generator, None)
            
            if test_chunk is not None:
                self.voice = new_voice
                voice_ai.current_voice = new_voice
                logger.info(f"Voice switched to: {new_voice}")
                return True
            else:
                logger.error(f"Voice test failed for: {new_voice}")
                return False
                
        except Exception as e:
            logger.error(f"Voice switch failed: {e}")
            return False

# Export
__all__ = ['SpeechProcessor']