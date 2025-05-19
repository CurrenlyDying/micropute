#!/usr/bin/env python3

import os
import signal
import time
import datetime
import logging
import sounddevice as sd
from scipy.io.wavfile import write
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='/var/log/mic_recorder.log',
    filemode='a'
)
logger = logging.getLogger('mic_recorder')

# Audio recording parameters
RATE = 44100  # Sample rate (Hz)
CHANNELS = 1  # Mono recording
OUTPUT_DIR = '/var/lib/mic_recorder'
SEGMENT_DURATION_SECONDS = 30 * 60  # 30 minutes
CHUNK_DURATION = 5  # 5 seconds per chunk

# Ensure the output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Global flag to control recording
keep_recording = True

# Signal handler for graceful shutdown
def signal_handler(sig, frame):
    global keep_recording
    logger.info(f"Received signal {sig}. Stopping recording gracefully...")
    keep_recording = False

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def get_timestamp():
    """Generate a timestamp for filenames"""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def list_audio_devices():
    """List all available audio devices and log them"""
    try:
        devices = sd.query_devices()
        logger.info("Available audio devices:")
        
        input_devices = []
        for i, device in enumerate(devices):
            device_info = f"Device {i}: {device['name']}, inputs: {device['max_input_channels']}"
            logger.info(device_info)
            
            if device['max_input_channels'] > 0:
                input_devices.append((i, device['name'], device['max_input_channels']))
        
        return input_devices
    except Exception as e:
        logger.error(f"Error listing audio devices: {e}")
        return []

def find_best_input_device():
    """Find the best available input device"""
    try:
        input_devices = list_audio_devices()
        
        if not input_devices:
            logger.error("No input devices found")
            return None
        
        # Try to get the default input device
        try:
            default_device = sd.query_devices(kind='input')
            default_id = default_device['index']
            logger.info(f"Default input device: {default_id} - {default_device['name']}")
            
            # Check if default device has inputs
            if default_device['max_input_channels'] > 0:
                return default_id
        except Exception as e:
            logger.warning(f"Could not determine default input device: {e}")
        
        # If no default or default has no inputs, use the first available input device
        logger.info(f"Using first available input device: {input_devices[0][0]} - {input_devices[0][1]}")
        return input_devices[0][0]  # Return the device ID of the first input device
        
    except Exception as e:
        logger.error(f"Error finding input device: {e}")
        return None

def record_segment(device_id, duration, output_path):
    """Record audio for specified duration using shorter segments"""
    try:
        logger.info(f"Starting recording to {output_path} using device {device_id}")
        
        # We'll record in smaller chunks to be able to stop recording on signal
        total_chunks = int(duration / CHUNK_DURATION)
        all_recordings = []
        
        logger.info(f"Recording started for up to {duration} seconds...")
        segment_start_time = time.time()
        
        for chunk in range(total_chunks):
            if not keep_recording:
                logger.info("Recording stopped due to signal.")
                break
                
            # Record a smaller chunk
            chunk_frames = int(CHUNK_DURATION * RATE)
            try:
                # Use blocking mode for simplicity
                recording_chunk = sd.rec(
                    frames=chunk_frames,
                    samplerate=RATE,
                    channels=CHANNELS,
                    device=device_id,
                    blocking=True
                )
                all_recordings.append(recording_chunk)
                
                # Only log every 12 chunks (approximately every minute) to avoid log spam
                if chunk % 12 == 0 or chunk == total_chunks - 1:
                    logger.info(f"Recorded chunk {chunk+1}/{total_chunks} (approx. {(chunk+1)*CHUNK_DURATION/60:.1f} minutes)")
            except Exception as e:
                logger.error(f"Error recording chunk {chunk+1}: {e}")
                # Continue to next chunk
        
        # Calculate actual recording duration and combine chunks
        actual_duration = min(duration, time.time() - segment_start_time)
        logger.info(f"Recorded for {actual_duration:.2f} seconds, combining chunks...")
        
        if not all_recordings:
            logger.error("No audio was recorded")
            return False
            
        # Combine all chunks
        complete_recording = np.vstack(all_recordings)
        
        # Normalize the audio to prevent clipping
        max_val = np.max(np.abs(complete_recording))
        if max_val > 0:  # Avoid division by zero
            normalized_recording = complete_recording * (0.9 / max_val)
        else:
            normalized_recording = complete_recording
        
        # Convert to int16 format
        scaled = np.int16(normalized_recording * 32767)
        
        # Save to WAV file
        write(output_path, RATE, scaled)
        
        logger.info(f"Successfully saved recording to {output_path}")
        return True
    
    except Exception as e:
        logger.error(f"Error during recording: {e}", exc_info=True)
        return False

def record_audio():
    """Main recording function, creates a new file every SEGMENT_DURATION_SECONDS."""
    global keep_recording
    
    try:
        # Find a suitable input device
        device_id = find_best_input_device()
        if device_id is None:
            logger.critical("No suitable input device found, cannot record audio")
            return
        
        logger.info(f"Starting audio recording service using device {device_id}")
        
        # Continue recording segments until told to stop
        while keep_recording:
            timestamp = get_timestamp()
            output_path = os.path.join(OUTPUT_DIR, f"recording_{timestamp}.wav")
            
            # Record a segment
            success = record_segment(device_id, SEGMENT_DURATION_SECONDS, output_path)
            
            # If recording was stopped by a signal, exit loop
            if not keep_recording:
                logger.info("Recording stopped by signal.")
                break
                
            # If recording failed for some other reason, wait a bit and try again
            if not success:
                logger.warning("Segment recording failed, waiting 5 seconds before retrying.")
                time.sleep(5)
                
                # Try to find a device again in case it was disconnected/reconnected
                device_id = find_best_input_device()
                if device_id is None:
                    logger.critical("No suitable input device found after failure, stopping recording service")
                    break
    
    except Exception as e:
        logger.critical(f"A critical error occurred in the main recording function: {e}", exc_info=True)
    finally:
        logger.info("Recording service stopped.")

if __name__ == "__main__":
    record_audio()