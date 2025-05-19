#!/usr/bin/env python3

import os
import signal
import time
import datetime
import logging
import subprocess
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='/var/log/mic_recorder.log',
    filemode='a'
)
logger = logging.getLogger('mic_recorder')

# Audio recording parameters
OUTPUT_DIR = '/var/lib/mic_recorder'
SEGMENT_DURATION_SECONDS = 30 * 60  # 30 minutes

# Ensure the output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Global flags and process
keep_recording = True
current_process = None

# Signal handler for graceful shutdown
def signal_handler(sig, frame):
    global keep_recording, current_process
    logger.info(f"Received signal {sig}. Stopping recording gracefully...")
    keep_recording = False
    if current_process:
        try:
            current_process.terminate()
        except Exception as e:
            logger.error(f"Error terminating process: {e}")

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def get_timestamp():
    """Generate a timestamp for filenames"""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def check_alsa_devices():
    """Check available ALSA devices"""
    try:
        result = subprocess.run(['arecord', '-l'], capture_output=True, text=True)
        logger.info(f"ALSA devices: {result.stdout}")
        return "card 1" in result.stdout or "HyperX Quadcast" in result.stdout
    except Exception as e:
        logger.error(f"Error checking ALSA devices: {e}")
        return False

def record_segment(output_path, duration=SEGMENT_DURATION_SECONDS):
    """Record a single audio segment using arecord"""
    global current_process

    try:
        logger.info(f"Starting recording to {output_path}")
        
        # Use arecord with the HyperX Quadcast device
        cmd = [
            'arecord',
            '-f', 'cd',          # CD quality (16-bit, 44100 Hz)
            '-t', 'wav',         # WAV format
            '-D', 'hw:1,0',      # Use the HyperX Quadcast device
            '-d', str(duration), # Duration in seconds
            output_path          # Output file
        ]
        
        current_process = subprocess.Popen(cmd)
        
        # Wait for the recording to complete or for an interrupt
        current_process.wait()
        
        if current_process.returncode == 0:
            logger.info(f"Successfully recorded segment to {output_path}")
            return True
        else:
            logger.error(f"Recording failed with return code {current_process.returncode}")
            return False
    
    except Exception as e:
        logger.error(f"Error during recording: {e}")
        return False
    finally:
        current_process = None

def record_audio():
    """Main recording function, creates a new file every SEGMENT_DURATION_SECONDS."""
    global keep_recording

    try:
        # Check if ALSA devices are available
        if not check_alsa_devices():
            logger.critical("No suitable recording device found.")
            return

        logger.info("Starting audio recording service.")
        
        # Continue recording segments until told to stop
        while keep_recording:
            timestamp = get_timestamp()
            output_path = os.path.join(OUTPUT_DIR, f"recording_{timestamp}.wav")
            
            # Record a segment
            success = record_segment(output_path)
            
            # If recording was stopped by a signal, exit loop
            if not keep_recording:
                logger.info("Recording stopped by signal.")
                break
                
            # If recording failed for some other reason, wait a bit and try again
            if not success:
                logger.warning("Segment recording failed, waiting 5 seconds before retrying.")
                time.sleep(5)
                
    except Exception as e:
        logger.critical(f"A critical error occurred in the main recording function: {e}", exc_info=True)
    finally:
        logger.info("Recording service stopped.")

if __name__ == "__main__":
    record_audio() 