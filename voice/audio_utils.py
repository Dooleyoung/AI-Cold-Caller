"""
Audio utilities for format conversion and processing
"""
import numpy as np
import soundfile as sf
import tempfile
import os
from typing import Optional, Tuple
from utils.logger import get_logger

logger = get_logger(__name__)

def convert_sample_rate(audio_data: np.ndarray, original_rate: int, target_rate: int) -> np.ndarray:
    """Convert audio sample rate using librosa"""
    try:
        import librosa
        return librosa.resample(audio_data, orig_sr=original_rate, target_sr=target_rate)
    except ImportError:
        logger.warning("librosa not available, sample rate conversion skipped")
        return audio_data
    except Exception as e:
        logger.error(f"Sample rate conversion failed: {e}")
        return audio_data

def ensure_mono(audio_data: np.ndarray) -> np.ndarray:
    """Ensure audio is mono (single channel)"""
    if len(audio_data.shape) > 1:
        return np.mean(audio_data, axis=1)
    return audio_data

def normalize_audio(audio_data: np.ndarray, target_level: float = 0.7) -> np.ndarray:
    """Normalize audio to target level"""
    if len(audio_data) == 0:
        return audio_data
    
    max_val = np.max(np.abs(audio_data))
    if max_val > 0:
        return audio_data * (target_level / max_val)
    return audio_data

def save_audio_for_twilio(audio_data: np.ndarray, sample_rate: int = 24000) -> str:
    """Save audio in format compatible with Twilio"""
    try:
        # Ensure mono
        audio_data = ensure_mono(audio_data)
        
        # Convert to 8kHz for Twilio (optimal for phone calls)
        if sample_rate != 8000:
            audio_data = convert_sample_rate(audio_data, sample_rate, 8000)
        
        # Normalize
        audio_data = normalize_audio(audio_data)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            sf.write(tmp_file.name, audio_data, 8000, subtype='PCM_16')
            return tmp_file.name
            
    except Exception as e:
        logger.error(f"Error saving audio for Twilio: {e}")
        raise

def validate_audio_format(file_path: str) -> bool:
    """Validate if audio file is in supported format"""
    try:
        data, sample_rate = sf.read(file_path)
        return len(data) > 0 and sample_rate > 0
    except Exception as e:
        logger.error(f"Audio validation failed for {file_path}: {e}")
        return False

# Export
__all__ = ['convert_sample_rate', 'ensure_mono', 'normalize_audio', 'save_audio_for_twilio', 'validate_audio_format']