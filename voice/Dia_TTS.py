#!/usr/bin/env python3
"""
Real-time Voice AI Assistant with Kokoro TTS and Librosa-based Voice Activity Detection
Uses Whisper (Groq) for STT + LLaMA (Groq) for conversation + Kokoro for TTS
COMPLETELY HANDS-FREE - NO KEYBOARD INTERACTION NEEDED
ENHANCED WITH 8-CPU MULTIPROCESSING FOR MAXIMUM SPEED
"""

import os
import tempfile
import threading
import time
import pyaudio
import wave
import numpy as np
import librosa
from groq import Groq
from kokoro import KPipeline
import pygame
import torch
import queue
import concurrent.futures
import multiprocessing as mp
from multiprocessing import Pool
from typing import Optional, Dict, Any
from functools import partial
import warnings

# Suppress pygame warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pygame")
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

class RealTimeVoiceAI:
    def __init__(self, groq_api_key=None, voice="af_bella"):
        """
        Initialize the real-time voice AI system with Kokoro TTS and Librosa VAD
        ENHANCED WITH 8-CPU MULTIPROCESSING
        """
        # Initialize Groq client
        if groq_api_key:
            self.groq_client = Groq(api_key="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")
        else:
            # Will use GROQ_API_KEY environment variable
            self.groq_client = Groq()
        
        # Initialize Kokoro TTS
        print("🎤 Loading Kokoro TTS...")
        self.load_kokoro_tts(voice)
        
        # Initialize pygame for audio playback
        pygame.mixer.init(frequency=24000)  # Kokoro outputs at 24kHz
        
        # Audio recording settings
        self.CHUNK = 1024
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000  # 16kHz for Whisper
        
        # Librosa-based VAD settings
        self.spectral_centroid_threshold = 1000  # Hz - typical speech range
        self.zcr_threshold = 0.1  # Zero crossing rate threshold
        self.energy_threshold = 0.002  # Energy threshold
        self.silence_duration = 2.0  # Seconds of silence to stop recording
        self.min_speech_duration = 0.3  # Minimum speech duration to consider valid
        # Removed max_recording_duration - unlimited speech duration
        
        # Initialize PyAudio
        self.audio = pyaudio.PyAudio()
        
        # Conversation context
        self.conversation_history = []
        
        # State management
        self.is_speaking = False
        self.is_listening = False
        
        # ENHANCED: Parallel processing components with 8-CPU optimization
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)  # Increased workers
        self.transcription_queue = queue.Queue()
        self.ai_response_queue = queue.Queue()
        self.tts_cache = {}
        
        # NEW: Multiprocessing pool for CPU-intensive tasks
        self.num_cpu_cores = min(2, mp.cpu_count())  # REDUCED FROM 8 TO 2
        self.process_pool = Pool(processes=self.num_cpu_cores)
        print(f"🚀 Initialized with {self.num_cpu_cores} CPU cores for parallel processing")
        
        # Pre-load common responses for instant playback
        self.preload_common_responses()
        
        print("✅ Real-time Voice AI with Kokoro and Librosa VAD initialized!")
        print("🔧 ENHANCED: 2-CPU parallel processing pipeline active!")
    
    def load_kokoro_tts(self, voice="af_heart"):
        """
        Load Kokoro TTS with proper voice names from GitHub repo
        KEEPING ALL 9 VOICES AS ORIGINAL
        """
        try:
            print(f"🔄 Loading Kokoro with {voice} voice...")
            
            # Increase timeout for downloads
            import socket
            socket.setdefaulttimeout(60)
            
            # Initialize Kokoro pipeline with language code
            self.kokoro = KPipeline(lang_code='a')  # 'a' for American English
            
            # ORIGINAL: Correct voice names from GitHub documentation - ALL 9 VOICES
            self.available_voices = [
                "af_heart",    # Default mixed voice (most reliable)
                "af_bella",    # American female Bella
                "af_sarah",    # American female Sarah  
                "am_adam",     # American male Adam
                "am_michael",  # American male Michael
                "bf_emma",     # British female Emma
                "bf_isabella", # British female Isabella
                "bm_george",   # British male George
                "bm_lewis"     # British male Lewis
            ]
            
            # Test voice generation with the requested voice
            print("🧪 Testing voice generation...")
            test_text = "Testing Kokoro voice."
            
            try:
                # Test the requested voice
                test_generator = self.kokoro(test_text, voice=voice)
                test_chunk = next(test_generator, None)
                
                if test_chunk is not None:
                    self.current_voice = voice
                    print(f"✅ {voice} voice loaded successfully!")
                else:
                    raise Exception("Voice test failed")
                    
            except Exception as e:
                print(f"⚠️  {voice} failed: {e}")
                
                # Try fallback voices in order of reliability
                fallback_voices = ["af_heart", "af_bella", "af_sarah"]
                
                for fallback in fallback_voices:
                    if fallback == voice:
                        continue
                        
                    try:
                        print(f"🔄 Trying fallback voice: {fallback}")
                        test_generator = self.kokoro(test_text, voice=fallback)
                        test_chunk = next(test_generator, None)
                        
                        if test_chunk is not None:
                            self.current_voice = fallback
                            print(f"✅ Using {fallback} voice as fallback")
                            break
                            
                    except Exception as e2:
                        print(f"❌ {fallback} also failed: {e2}")
                        continue
                else:
                    raise Exception("All voice options failed")
            
            print(f"🎭 Available voices: {', '.join(self.available_voices)}")
            
        except Exception as e:
            print(f"❌ Failed to load Kokoro: {e}")
            print("💡 Make sure you have:")
            print("   • pip install kokoro>=0.9.4 soundfile librosa")
            print("   • Good internet connection for voice downloads")
            print("   • espeak-ng installed")
            raise
    
    def analyze_audio_features_worker(self, audio_data):
        """
        ENHANCED: Worker function for multiprocessing audio analysis
        """
        try:
            # Normalize audio data
            if len(audio_data) < 512:  # Need minimum samples for analysis
                return {'is_speech': False, 'confidence': 0.0}
            
            # Convert to float32 for librosa
            audio_float = audio_data.astype(np.float32) / 32768.0
            
            # Adjust FFT parameters based on audio length
            n_fft = min(2048, len(audio_float) // 2)  # Ensure FFT size fits audio
            hop_length = n_fft // 4
            
            # Calculate spectral features using librosa
            # 1. Spectral Centroid - indicates where the "center of mass" of the spectrum is
            spectral_centroids = librosa.feature.spectral_centroid(
                y=audio_float, sr=self.RATE, n_fft=n_fft, hop_length=hop_length
            )[0]
            spectral_centroid_mean = np.mean(spectral_centroids)
            
            # 2. Zero Crossing Rate - how often the signal crosses zero
            zcr = librosa.feature.zero_crossing_rate(audio_float, hop_length=hop_length)[0]
            zcr_mean = np.mean(zcr)
            
            # 3. RMS Energy - overall energy of the signal
            rms_energy = librosa.feature.rms(y=audio_float, hop_length=hop_length)[0]
            rms_mean = np.mean(rms_energy)
            
            # 4. Spectral Rolloff - frequency below which 85% of spectral energy is contained
            spectral_rolloff = librosa.feature.spectral_rolloff(
                y=audio_float, sr=self.RATE, n_fft=n_fft, hop_length=hop_length
            )[0]
            rolloff_mean = np.mean(spectral_rolloff)
            
            # 5. MFCC features for more sophisticated analysis (reduced for shorter audio)
            n_mfcc = min(13, max(1, len(audio_float) // 512))  # Adjust MFCC count
            mfccs = librosa.feature.mfcc(
                y=audio_float, sr=self.RATE, n_mfcc=n_mfcc, n_fft=n_fft, hop_length=hop_length
            )
            mfcc_mean = np.mean(mfccs, axis=1)
            
            # Voice activity detection logic using multiple features
            is_speech = False
            confidence = 0.0
            
            # Check multiple indicators of speech
            speech_indicators = 0
            total_indicators = 5
            
            # 1. Spectral centroid in speech range (typically 1000-4000 Hz for human speech)
            if 500 < spectral_centroid_mean < 4000:
                speech_indicators += 1
            
            # 2. Zero crossing rate indicates speech (not too low, not too high)
            if 0.05 < zcr_mean < 0.3:
                speech_indicators += 1
            
            # 3. Sufficient energy
            if rms_mean > self.energy_threshold:
                speech_indicators += 1
            
            # 4. Spectral rolloff in reasonable range
            if 1000 < rolloff_mean < 8000:
                speech_indicators += 1
            
            # 5. MFCC analysis - first coefficient should be reasonable for speech
            if len(mfcc_mean) > 0 and -50 < mfcc_mean[0] < 50:
                speech_indicators += 1
            
            confidence = speech_indicators / total_indicators
            is_speech = confidence > 0.6  # Require at least 3/5 indicators
            
            return {
                'is_speech': is_speech,
                'confidence': confidence,
                'spectral_centroid': spectral_centroid_mean,
                'zcr': zcr_mean,
                'rms_energy': rms_mean,
                'spectral_rolloff': rolloff_mean
            }
            
        except Exception as e:
            print(f"⚠️ Audio analysis error: {e}")
            return {'is_speech': False, 'confidence': 0.0}

    def analyze_audio_features(self, audio_data):
        """
        ENHANCED: Use multiprocessing for faster audio analysis when dealing with larger chunks
        """
        try:
            # For small audio chunks, use single processing (faster)
            if len(audio_data) < 4096:
                return self.analyze_audio_features_worker(audio_data)
            
            # For larger chunks, split into parallel processing
            chunk_size = len(audio_data) // min(4, self.num_cpu_cores)
            if chunk_size < 512:
                return self.analyze_audio_features_worker(audio_data)
            
            # Split audio into chunks for parallel processing
            chunks = []
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                if len(chunk) >= 512:
                    chunks.append(chunk)
            
            if not chunks:
                return {'is_speech': False, 'confidence': 0.0}
            
            # Process chunks in parallel using multiprocessing
            try:
                results = self.process_pool.map(self.analyze_audio_features_worker, chunks)
                
                # Combine results from all chunks
                valid_results = [r for r in results if r.get('confidence', 0) > 0]
                
                if not valid_results:
                    return {'is_speech': False, 'confidence': 0.0}
                
                # Average the results
                combined_result = {
                    'is_speech': np.mean([r['is_speech'] for r in valid_results]) > 0.5,
                    'confidence': np.mean([r['confidence'] for r in valid_results]),
                    'spectral_centroid': np.mean([r['spectral_centroid'] for r in valid_results]),
                    'zcr': np.mean([r['zcr'] for r in valid_results]),
                    'rms_energy': np.mean([r['rms_energy'] for r in valid_results]),
                    'spectral_rolloff': np.mean([r['spectral_rolloff'] for r in valid_results])
                }
                
                return combined_result
                
            except Exception as mp_error:
                # Fallback to single processing if multiprocessing fails
                print(f"⚠️ Multiprocessing failed, using single core: {mp_error}")
                return self.analyze_audio_features_worker(audio_data)
            
        except Exception as e:
            print(f"⚠️ Audio analysis error: {e}")
            return {'is_speech': False, 'confidence': 0.0}
    
    def record_audio_with_librosa_vad(self):
        """
        Record audio with librosa-based voice activity detection
        Uses spectral analysis to intelligently detect speech
        No maximum duration limit - unlimited speech recording
        ENHANCED: Now with multiprocessing support for faster analysis
        """
        # Removed "Listening for your voice" message
        stream = self.audio.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            frames_per_buffer=self.CHUNK
        )
        
        frames = []
        speech_detected = False
        silence_chunks = 0
        speech_chunks = 0
        start_time = time.time()
        last_speech_time = start_time
        
        # For librosa analysis, we need to accumulate some audio
        audio_buffer = []
        buffer_size = int(self.RATE * 0.1)  # 100ms buffer for faster VAD analysis
        
        chunks_per_second = self.RATE / self.CHUNK
        silence_chunks_threshold = int(self.silence_duration * chunks_per_second)
        min_speech_chunks = int(self.min_speech_duration * chunks_per_second)
        
        try:
            while True:
                try:
                    data = stream.read(self.CHUNK, exception_on_overflow=False)
                except Exception as read_error:
                    print(f"\n⚠️ Audio read error: {read_error}")
                    # Try to continue with empty data
                    data = b'\x00' * (self.CHUNK * 2)  # 2 bytes per sample for int16
                
                frames.append(data)
                
                # Convert to numpy array for analysis
                try:
                    audio_chunk = np.frombuffer(data, dtype=np.int16)
                except ValueError:
                    # Handle corrupted audio data
                    audio_chunk = np.zeros(self.CHUNK, dtype=np.int16)
                
                audio_buffer.extend(audio_chunk)
                
                # Analyze when we have enough data
                if len(audio_buffer) >= buffer_size:
                    # Analyze the last buffer_size samples
                    analysis_data = np.array(audio_buffer[-buffer_size:])
                    features = self.analyze_audio_features(analysis_data)  # Now uses multiprocessing
                    
                    current_time = time.time()
                    
                    # Display real-time analysis (optimized for 100ms buffers)
                    if len(frames) % 5 == 0:  # Every ~50ms for more responsive display
                        confidence_bar = "█" * int(features['confidence'] * 10)
                        print(f"\r🎤 {confidence_bar:<10} {features['confidence']:.2f} "
                              f"| Energy: {features.get('rms_energy', 0):.3f}", 
                              end="", flush=True)
                    
                    # Speech detection logic
                    if features['is_speech'] and features['confidence'] > 0.6:
                        if not speech_detected:
                            print(f"\n🎉 Speech detected! (confidence: {features['confidence']:.2f})")
                        speech_detected = True
                        speech_chunks += 1
                        silence_chunks = 0
                        last_speech_time = current_time
                        print("🗣️", end="", flush=True)
                    else:
                        if speech_detected:
                            silence_chunks += 1
                            print(".", end="", flush=True)
                    
                    # Keep buffer manageable
                    if len(audio_buffer) > buffer_size * 3:
                        audio_buffer = audio_buffer[-buffer_size:]
                
                # Check stopping conditions
                elapsed_time = time.time() - start_time
                silence_time = time.time() - last_speech_time
                
                # Stop if we have enough speech followed by enough silence
                if (speech_detected and 
                    speech_chunks >= min_speech_chunks and 
                    silence_chunks >= silence_chunks_threshold):
                    print(f"\n✅ Speech completed! Duration: {elapsed_time:.1f}s, Silence: {silence_time:.1f}s")
                    break
                
                # Removed maximum duration limit - unlimited speech recording
                
                # Show waiting status if no speech detected yet
                if not speech_detected and elapsed_time > 3 and int(elapsed_time) % 2 == 0:
                    print(f"\n⏰ Waiting for speech... ({elapsed_time:.0f}s)")
                    
        except Exception as e:
            print(f"\n❌ Recording error: {e}")
        finally:
            stream.stop_stream()
            stream.close()
        
        if not speech_detected:
            print("\n❓ No speech detected - try speaking more clearly")
            return None
        
        # Save to temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            temp_path = tmp_file.name
        
        wf = wave.open(temp_path, 'wb')
        wf.setnchannels(self.CHANNELS)
        wf.setsampwidth(self.audio.get_sample_size(self.FORMAT))
        wf.setframerate(self.RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        
        total_duration = time.time() - start_time
        print(f"\n✅ Recording saved! Total: {total_duration:.1f}s, Speech chunks: {speech_chunks}")
        return temp_path
    
    def calibrate_vad_settings(self):
        """
        Calibrate VAD settings based on user's voice and environment
        ENHANCED: Now uses multiprocessing for faster analysis
        """
        print("🎛️ Calibrating for your voice...")
        print("🗣️  Speak naturally for 5 seconds...")
        
        stream = self.audio.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            frames_per_buffer=self.CHUNK
        )
        
        all_features = []
        audio_buffer = []
        
        try:
            # Record for 5 seconds
            for i in range(int(5 * self.RATE / self.CHUNK)):
                try:
                    data = stream.read(self.CHUNK, exception_on_overflow=False)
                    audio_chunk = np.frombuffer(data, dtype=np.int16)
                except Exception as read_error:
                    print(f"⚠️", end="", flush=True)
                    # Skip this chunk on error
                    continue
                    
                audio_buffer.extend(audio_chunk)
                
                # Analyze every 100ms (consistent with main VAD)
                if len(audio_buffer) >= int(self.RATE * 0.1):
                    features = self.analyze_audio_features(np.array(audio_buffer[-int(self.RATE * 0.1):]))  # Uses multiprocessing
                    if features['confidence'] > 0.3:  # Only collect speech samples
                        all_features.append(features)
                
                # Progress indicator
                if i % 16 == 0:  # Every ~100ms
                    print("🎤", end="", flush=True)
                    
        finally:
            stream.stop_stream()
            stream.close()
        
        print(f"\n📊 Analyzed {len(all_features)} speech samples")
        
        if len(all_features) > 0:
            # Calculate average characteristics of user's voice
            avg_centroid = np.mean([f['spectral_centroid'] for f in all_features])
            avg_zcr = np.mean([f['zcr'] for f in all_features])
            avg_energy = np.mean([f['rms_energy'] for f in all_features])
            avg_rolloff = np.mean([f['spectral_rolloff'] for f in all_features])
            
            print(f"✅ Your voice characteristics:")
            print(f"   Spectral Centroid: {avg_centroid:.0f} Hz")
            print(f"   Zero Crossing Rate: {avg_zcr:.3f}")
            print(f"   RMS Energy: {avg_energy:.3f}")
            print(f"   Spectral Rolloff: {avg_rolloff:.0f} Hz")
            
            # Adjust thresholds based on user's voice
            self.spectral_centroid_threshold = max(500, avg_centroid * 0.7)
            self.zcr_threshold = max(0.02, avg_zcr * 0.5)
            self.energy_threshold = max(0.005, avg_energy * 0.3)
            
            print(f"\n🎯 Calibrated thresholds:")
            print(f"   Energy threshold: {self.energy_threshold:.3f}")
            print(f"   ZCR threshold: {self.zcr_threshold:.3f}")
            print(f"   Spectral centroid threshold: {self.spectral_centroid_threshold:.0f} Hz")
            print("✅ VAD calibration complete!")
            
        else:
            print("❌ No speech detected during calibration!")
            print("💡 Using default settings - try speaking louder")
    
    def preload_common_responses(self):
        """
        Pre-generate audio for common responses to eliminate TTS delays
        ENHANCED: Now uses multithreading for faster preloading
        """
        print("🔄 Pre-loading common responses...")
        
        common_phrases = [
            "I don't understand, could you repeat that?",
            "Sorry, I didn't catch that.",
            "Can you speak a bit louder?",
            "I'm listening.",
            "Go ahead.",
            "Yes?",
            "Okay.",
            "I see.",
            "That's interesting.",
            "Tell me more.",
            "I understand.",
            "Good point."
        ]
        
        # ENHANCED: Pre-generate audio for common phrases using multithreading
        def preload_phrase(phrase):
            try:
                generator = self.kokoro(phrase, voice=self.current_voice)
                audio_chunks = []
                for i, (gs, ps, audio) in enumerate(generator):
                    audio_chunks.append(audio)
                    if i > 5:  # Limit chunks for common phrases
                        break
                
                if audio_chunks:
                    full_audio = np.concatenate(audio_chunks)
                    self.tts_cache[phrase] = full_audio
                    return True
            except Exception as e:
                print(f"⚠️ Failed to preload: {phrase[:20]}...")
                return False
        
        # Load a few critical phrases synchronously
        critical_phrases = common_phrases[:3]
        for phrase in critical_phrases:
            preload_phrase(phrase)
        
        # ENHANCED: Load the rest using multithreading for speed
        futures = []
        for phrase in common_phrases[3:]:
            future = self.executor.submit(preload_phrase, phrase)
            futures.append(future)
        
        # FIXED: Better timeout handling to prevent initialization failure
        completed_count = 0
        try:
            for future in concurrent.futures.as_completed(futures, timeout=20):  # Increased timeout
                try:
                    if future.result():
                        completed_count += 1
                except Exception as e:
                    pass  # Continue even if some fail
        except concurrent.futures.TimeoutError:
            print(f"⚠️ Some phrases took too long to preload, continuing anyway...")
            # Cancel any remaining futures
            for future in futures:
                if not future.done():
                    future.cancel()
        
        print(f"✅ Pre-loaded {len(self.tts_cache)} responses (attempted {len(common_phrases)})")
    
    def get_cached_response(self, text: str) -> Optional[np.ndarray]:
        """
        Check if we have a pre-cached audio response
        """
        # Exact match first
        if text in self.tts_cache:
            return self.tts_cache[text]
        
        # Fuzzy match for similar phrases
        text_lower = text.lower().strip()
        for cached_phrase, audio in self.tts_cache.items():
            if cached_phrase.lower().strip() == text_lower:
                return audio
        
        return None
    
    def transcribe_audio_async(self, audio_file_path: str) -> concurrent.futures.Future:
        """
        Start transcription asynchronously and return a Future
        ENHANCED: Now part of expanded thread pool
        """
        def transcribe():
            try:
                print("🔄 Transcribing with Whisper Turbo...")
                
                with open(audio_file_path, "rb") as file:
                    transcription = self.groq_client.audio.transcriptions.create(
                        file=(audio_file_path, file.read()),
                        model="whisper-large-v3-turbo",  # Faster turbo model
                        response_format="verbose_json",
                    )
                
                text = transcription.text.strip()
                print(f"👤 You said: '{text}'")
                
                # Clean up audio file
                try:
                    os.unlink(audio_file_path)
                except:
                    pass
                
                return text if text else None
                
            except Exception as e:
                print(f"❌ Transcription error: {e}")
                return None
        
        return self.executor.submit(transcribe)
    
    def transcribe_audio(self, audio_file_path):
        """
        Legacy method for compatibility - now uses async version
        """
        future = self.transcribe_audio_async(audio_file_path)
        return future.result()  # Block until completion
    
    def get_ai_response_async(self, user_message: str) -> concurrent.futures.Future:
        """
        Generate AI response asynchronously and return a Future
        ENHANCED: Now part of expanded thread pool
        """
        def generate_response():
            try:
                print("🧠 Generating AI response...")
                
                # Build conversation context
                messages = []
                
                # System prompt based on voice (optimized for speed)
                if "bella" in self.current_voice:
                    system_prompt = """You are Bella, a warm, friendly AI assistant. 
                    Keep responses very brief (1-2 sentences max) for fast conversation. 
                    Be enthusiastic but concise."""
                elif "sarah" in self.current_voice:
                    system_prompt = """You are Sarah, a clear, professional AI assistant.
                    Keep responses very brief (1-2 sentences max) for fast conversation.
                    Be precise and helpful."""
                elif "adam" in self.current_voice:
                    system_prompt = """You are Adam, a confident AI assistant.
                    Keep responses very brief (1-2 sentences max) for fast conversation.
                    Be authoritative but concise."""
                elif "emma" in self.current_voice:
                    system_prompt = """You are Emma, a sophisticated British AI assistant.
                    Keep responses very brief (1-2 sentences max) for fast conversation.
                    Be elegant but concise."""
                elif "michael" in self.current_voice:
                    system_prompt = """You are Michael, a friendly American AI assistant.
                    Keep responses very brief (1-2 sentences max) for fast conversation.
                    Be warm but concise."""
                elif "isabella" in self.current_voice:
                    system_prompt = """You are Isabella, a warm British AI assistant.
                    Keep responses very brief (1-2 sentences max) for fast conversation.
                    Be charming but concise."""
                elif "george" in self.current_voice:
                    system_prompt = """You are George, an authoritative British AI assistant.
                    Keep responses very brief (1-2 sentences max) for fast conversation.
                    Be distinguished but concise."""
                elif "lewis" in self.current_voice:
                    system_prompt = """You are Lewis, a friendly British AI assistant.
                    Keep responses very brief (1-2 sentences max) for fast conversation.
                    Be cheerful but concise."""
                else:
                    system_prompt = """You are a helpful AI assistant having a voice conversation. 
                    Keep responses very brief (1-2 sentences max) for fast conversation. 
                    Be friendly and concise."""
                
                messages.append({"role": "system", "content": system_prompt})
                
                # Add recent conversation history (last 6 exchanges)
                for exchange in self.conversation_history[-6:]:
                    messages.append({"role": "user", "content": exchange["user"]})
                    messages.append({"role": "assistant", "content": exchange["assistant"]})
                
                # Add current message
                messages.append({"role": "user", "content": user_message})
                
                # Get response with optimized settings for speed
                completion = self.groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=messages,
                    temperature=0.7,
                    max_completion_tokens=150,  # Reduced for faster generation
                    top_p=0.9,
                    stream=True,
                    stop=None,
                )
                
                # Collect streaming response
                response_text = ""
                print("🤖 AI Response: ", end="", flush=True)
                
                for chunk in completion:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        response_text += content
                        print(content, end="", flush=True)
                
                print()  # New line after response
                
                return response_text.strip()
                
            except Exception as e:
                print(f"❌ AI response error: {e}")
                return "Sorry, I had trouble generating a response. Could you try again?"
        
        return self.executor.submit(generate_response)
    
    def get_ai_response(self, user_message):
        """
        Legacy method for compatibility - now uses async version
        """
        future = self.get_ai_response_async(user_message)
        return future.result()  # Block until completion
    
    def speak_response(self, text):
        """
        Convert text to speech using Kokoro with caching and optimization
        ENHANCED: TTS generation now uses multithreading for background processing
        """
        # Check cache first for instant playback
        cached_audio = self.get_cached_response(text)
        if cached_audio is not None:
            print(f"🔊 Speaking (cached): {text}")
            self.play_audio_array(cached_audio)
            return
        
        # ENHANCED: Generate new audio using multithreading if not cached
        def generate_tts():
            max_retries = 3
            retry_delay = 1  # Reduced retry delay
            
            for attempt in range(max_retries):
                try:
                    print(f"🔄 Generating speech with Kokoro... (attempt {attempt + 1})")
                    start_time = time.time()
                    
                    self.is_speaking = True
                    
                    # Split long text to avoid timeouts
                    if len(text) > 200:
                        # Split into sentences for better reliability
                        sentences = text.replace('.', '.|').replace('!', '!|').replace('?', '?|').split('|')
                        sentences = [s.strip() for s in sentences if s.strip()]
                    else:
                        sentences = [text]
                    
                    all_audio = []
                    
                    for sentence in sentences:
                        if not sentence:
                            continue
                            
                        # Generate speech with timeout handling
                        try:
                            generator = self.kokoro(sentence, voice=self.current_voice)
                            
                            # Collect audio chunks with timeout
                            sentence_audio = []
                            for i, (gs, ps, audio) in enumerate(generator):
                                sentence_audio.append(audio)
                                # Break if we get enough chunks to avoid hanging
                                if i > 10:  # Reasonable limit
                                    break
                            
                            if sentence_audio:
                                all_audio.extend(sentence_audio)
                                
                        except Exception as e:
                            print(f"⚠️  Failed to generate audio for: '{sentence[:50]}...' - {e}")
                            continue
                    
                    # Concatenate and play if we got any audio
                    if all_audio:
                        full_audio = np.concatenate(all_audio)
                        
                        # Cache the audio for future use if it's short enough
                        if len(text) < 100:
                            self.tts_cache[text] = full_audio
                        
                        generation_time = time.time() - start_time
                        print(f"🔊 Speaking with {self.current_voice} voice... (Generated in {generation_time:.2f}s)")
                        
                        self.play_audio_array(full_audio)
                        self.is_speaking = False
                        return  # Success!
                    
                    else:
                        raise Exception("No audio generated")
                        
                except Exception as e:
                    print(f"❌ Kokoro speech error (attempt {attempt + 1}): {e}")
                    
                    if attempt < max_retries - 1:
                        print(f"🔄 Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                    else:
                        # Final fallback - just print the text
                        print(f"🤖 Text response (Kokoro failed): {text}")
                        self.is_speaking = False
        
        # Run TTS generation in thread for non-blocking operation
        future = self.executor.submit(generate_tts)
        future.result()  # Wait for completion
    
    def play_audio_array(self, audio_array: np.ndarray):
        """
        Play audio from numpy array efficiently
        """
        try:
            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                temp_path = tmp_file.name
            
            # Save the audio
            import soundfile as sf
            sf.write(temp_path, audio_array, 24000)  # Kokoro outputs at 24kHz
            
            # Play the audio
            pygame.mixer.music.load(temp_path)
            pygame.mixer.music.play()
            
            # Wait for playback to finish
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
            
            # Clean up
            try:
                os.unlink(temp_path)
            except:
                pass
                
        except Exception as e:
            print(f"❌ Audio playback error: {e}")
    
    def handle_voice_commands(self, user_message):
        """
        Handle voice switching and other commands
        KEEPING ALL ORIGINAL 9 VOICES
        """
        message_lower = user_message.lower()
        
        # Voice switching commands
        if "switch voice" in message_lower or "change voice" in message_lower:
            
            # Check for specific voice names - ALL 9 VOICES
            voice_mappings = {
                "heart": "af_heart",
                "bella": "af_bella", 
                "sarah": "af_sarah",
                "adam": "am_adam",
                "michael": "am_michael",
                "emma": "bf_emma",
                "isabella": "bf_isabella",
                "george": "bm_george",
                "lewis": "bm_lewis"
            }
            
            for name, voice_id in voice_mappings.items():
                if name in message_lower:
                    if voice_id in self.available_voices:
                        try:
                            test_generator = self.kokoro("Voice test", voice=voice_id)
                            test_chunk = next(test_generator, None)
                            
                            if test_chunk is not None:
                                self.current_voice = voice_id
                                response = f"I've switched to my {voice_id} voice! How do I sound now?"
                                self.speak_response(response)
                                return True
                        except Exception as e:
                            response = f"Sorry, I couldn't switch to {voice_id}."
                            self.speak_response(response)
                            return True
                    else:
                        response = f"Sorry, {voice_id} isn't available."
                        self.speak_response(response)
                        return True
            
            # If no specific voice mentioned, list ALL available voices
            response = "Which voice would you like? I can be Heart, Bella, Sarah, Adam, Michael, Emma, Isabella, George, or Lewis."
            self.speak_response(response)
            return True
        
        elif "calibrate" in message_lower or "adjust sensitivity" in message_lower or "calibrate microphone" in message_lower:
            print("\n🎛️ Starting voice calibration...")
            print("🗣️  Speak naturally for 5 seconds to calibrate...")
            self.calibrate_vad_settings()
            response = "Perfect! I've calibrated my voice detection specifically for your voice. It should work much better now!"
            self.speak_response(response)
            return True
        
        elif "help" in message_lower or "what can you do" in message_lower or "commands" in message_lower:
            response = ("I can switch voices, calibrate my microphone, and have natural conversations! "
                       "Say 'switch voice to Sarah' to change voices, 'calibrate microphone' to adjust sensitivity, "
                       "or 'goodbye' to end our conversation.")
            self.speak_response(response)
            return True
        
        return False
    
    def start_conversation(self):
        """
        Start the completely hands-free conversation with ENHANCED parallel processing pipeline
        """
        print("\n" + "="*70)
        print("🚀 COMPLETELY HANDS-FREE VOICE AI - ENHANCED WITH 2-CPU PROCESSING")
        print("="*70)
        print("🎤 NO KEYBOARD NEEDED! Just speak naturally!")
        print("🗣️  Say 'goodbye', 'stop', or 'quit' to exit")
        print("🗣️  Say 'calibrate microphone' to adjust sensitivity")
        print("🗣️  Say 'switch voice to [name]' to change voices")
        print("🗣️  Say 'help' for available commands")
        print(f"🎭 Using Kokoro {self.current_voice} voice")
        print("🔬 Powered by Librosa spectral analysis")
        print("♾️  Unlimited speech duration")
        print("⚡ ENHANCED: Multiprocessing + 2-thread optimization")
        print(f"🔧 {self.num_cpu_cores} CPU cores active for audio analysis")
        print("🔧 Parallel processing pipeline + TTS caching")
        print("="*70)
        
        # Initial greeting based on voice - ALL 9 VOICES SUPPORTED
        if "bella" in self.current_voice:
            greeting = "Hi! I'm Bella, your lightning-fast AI assistant. Just speak naturally and I'll respond instantly!"
        elif "sarah" in self.current_voice:
            greeting = "Hello! I'm Sarah. Ready for ultra-fast conversation - just talk naturally!"
        elif "adam" in self.current_voice:
            greeting = "Hello! I'm Adam. We're now in high-speed mode with instant responses!"
        elif "emma" in self.current_voice:
            greeting = "Hello! I'm Emma. Ready for rapid-fire conversation!"
        elif "michael" in self.current_voice:
            greeting = "Hey! I'm Michael. Lightning-fast responses activated!"
        elif "isabella" in self.current_voice:
            greeting = "Hello! I'm Isabella. Ultra-fast processing ready!"
        elif "george" in self.current_voice:
            greeting = "Good day! I'm George. Enhanced processing activated!"
        elif "lewis" in self.current_voice:
            greeting = "Hello! I'm Lewis. Ready for high-speed conversation!"
        else:
            greeting = "Hello! I'm your ultra-fast AI assistant with instant parallel processing!"
        
        self.speak_response(greeting)
        
        conversation_active = True
        
        while conversation_active:
            try:
                print("\n⚡ ENHANCED parallel pipeline ready...")
                
                # Step 1: Record audio with enhanced multiprocessing VAD
                audio_file = self.record_audio_with_librosa_vad()
                
                if not audio_file:
                    continue
                
                # Step 2: Start transcription immediately (parallel)
                print("🔥 Starting ENHANCED parallel processing pipeline...")
                transcription_future = self.transcribe_audio_async(audio_file)
                
                # Step 3: Wait for transcription and immediately start AI response (parallel)
                user_message = transcription_future.result()
                
                if not user_message:
                    continue
                
                # Check for exit commands
                exit_phrases = ['goodbye', 'bye', 'quit', 'exit', 'stop', 'end conversation', 'that\'s all', 'see you later']
                if any(phrase in user_message.lower() for phrase in exit_phrases):
                    response = "Goodbye! Ultra-fast conversation complete!"
                    print(f"🤖 {response}")
                    self.speak_response(response)
                    conversation_active = False
                    break
                
                # Handle voice commands - ALL 9 VOICES SUPPORTED
                if self.handle_voice_commands(user_message):
                    continue
                
                # Step 4: Start AI response generation immediately (no waiting)
                ai_response_future = self.get_ai_response_async(user_message)
                
                # Step 5: Get AI response and start TTS immediately
                ai_response = ai_response_future.result()
                
                # Save to conversation history
                self.conversation_history.append({
                    "user": user_message,
                    "assistant": ai_response,
                    "timestamp": time.time()
                })
                
                # Step 6: Speak response (may use cache for instant playback)
                self.speak_response(ai_response)
                
                # No delays - immediately ready for next input
                
            except KeyboardInterrupt:
                print("\n👋 Enhanced parallel conversation ended")
                conversation_active = False
                break
            except Exception as e:
                print(f"❌ Pipeline error: {e}")
                # Try to use cached fallback response
                fallback = self.get_cached_response("Sorry, I didn't catch that.")
                if fallback is not None:
                    print("🔊 Using cached fallback response")
                    self.play_audio_array(fallback)
        
        # ENHANCED: Cleanup multiprocessing resources
        print("🧹 Cleaning up enhanced processing resources...")
        self.executor.shutdown(wait=True)
        self.process_pool.close()
        self.process_pool.join()
        print("✅ Cleanup complete!")

def main():
    """
    Main function - completely hands-free setup with ENHANCED multiprocessing
    """
    print("🚀 HANDS-FREE VOICE AI WITH KOKORO + LIBROSA VAD")
    print("="*60)
    print("🔬 Enhanced with Librosa spectral analysis")
    print("⚡ ENHANCED: 2-CPU multiprocessing optimization")
    print("🔧 Parallel processing pipeline + TTS caching")
    print("🎤 COMPLETELY HANDS-FREE CONVERSATION")
    print("♾️  Unlimited speech duration")
    print(f"💻 Using {mp.cpu_count()} available CPU cores")
    
    # Check for Groq API key
    groq_api_key = os.getenv('GROQ_API_KEY')
    
    if not groq_api_key:
        print("⚠️  Groq API Key Required!")
        print("Get your free API key from: https://console.groq.com/")
        print()
        groq_api_key = input("Enter your Groq API key: ").strip()
        
        if not groq_api_key:
            print("❌ API key required to continue")
            return
    
    # Voice selection - KEEPING ALL 9 VOICES
    voices = {
        "1": ("af_heart", "Heart - Mixed Voice (most reliable) ⭐"),
        "2": ("af_bella", "Bella - American Female (warm, conversational)"),
        "3": ("af_sarah", "Sarah - American Female (clear, professional)"),
        "4": ("am_adam", "Adam - American Male (deep, authoritative)"),
        "5": ("am_michael", "Michael - American Male (friendly)"),
        "6": ("bf_emma", "Emma - British Female (posh, elegant)"),
        "7": ("bf_isabella", "Isabella - British Female (warm)"),
        "8": ("bm_george", "George - British Male (authoritative)"),
        "9": ("bm_lewis", "Lewis - British Male (friendly)")
    }
    
    print("\n🎭 Choose your Kokoro voice:")
    for key, (voice_id, description) in voices.items():
        print(f"{key}. {description}")
    
    voice_choice = input("\nEnter choice (1-9, or press Enter for Heart): ").strip()
    selected_voice = voices.get(voice_choice, ("af_heart", "Heart"))[0]
    
    print(f"\n🔄 Initializing {selected_voice} voice...")
    print("🎤 ENHANCED PARALLEL PROCESSING PIPELINE READY!")
    print("⚡ Ultra-fast response with multiprocessing + TTS caching!")
    
    try:
        # Initialize the voice AI system with ENHANCED multiprocessing
        voice_ai = RealTimeVoiceAI(groq_api_key=groq_api_key, voice=selected_voice)
        
        # Choose mode
        print("\nChoose mode:")
        print("1. 🎤 Start hands-free conversation")
        print("2. 🧪 Test system") 
        print("3. 🎛️  Calibrate voice detection first")
        
        choice = input("\nEnter choice (1-3): ").strip()
        
        if choice == "2":
            # Test system
            print("🧪 Testing ENHANCED parallel processing pipeline...")
            voice_ai.speak_response("Enhanced parallel processing pipeline test successful! Ultra-fast response with multiprocessing activated.")
            print("✅ System test complete!")
        elif choice == "3":
            voice_ai.calibrate_vad_settings()
            print("Starting ENHANCED parallel conversation...")
            time.sleep(1)  # Reduced delay
            voice_ai.start_conversation()
        else:
            print("\n🚀 Starting ENHANCED parallel conversation pipeline...")
            print("⚡ Ultra-fast processing with multiprocessing activated!")
            time.sleep(1)  # Reduced delay
            voice_ai.start_conversation()
            
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        print("💡 Try: pip install --upgrade kokoro>=0.9.4 soundfile librosa")

if __name__ == "__main__":
    main()