#!/usr/bin/env python3

import os
import signal
import time
import datetime
import wave
import logging
import pyaudio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='/var/log/mic_recorder.log',
    filemode='a'
)
logger = logging.getLogger('mic_recorder')

# Audio recording parameters
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
OUTPUT_DIR = '/var/lib/mic_recorder'

# Ensure the output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Global flag to control recording
keep_recording = True

# Signal handler for graceful shutdown
def signal_handler(sig, frame):
    global keep_recording
    logger.info("Received signal to terminate. Stopping recording...")
    keep_recording = False

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def get_timestamp():
    """Generate a timestamp for filenames"""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def record_audio():
    """Main recording function"""
    p = pyaudio.PyAudio()
    logger.info("Starting audio recording service")
    
    try:
        # Create a filename with timestamp for when the service starts
        timestamp = get_timestamp()
        wav_file = os.path.join(OUTPUT_DIR, f"recording_{timestamp}.wav")
        
        # Open the WAV file for writing
        wf = wave.open(wav_file, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        
        # Open stream
        stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)
        
        logger.info(f"Recording to {wav_file}")
        
        # Record continuously until service is stopped
        while keep_recording:
            data = stream.read(CHUNK, exception_on_overflow=False)
            wf.writeframes(data)
        
        # Stop and close the stream
        stream.stop_stream()
        stream.close()
        wf.close()
        
        logger.info(f"Recording saved to {wav_file}")
    
    except Exception as e:
        logger.error(f"Recording error: {e}")
    finally:
        # Clean up
        p.terminate()
        logger.info("Recording service stopped")

if __name__ == "__main__":
    record_audio() 