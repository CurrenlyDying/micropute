#!/usr/bin/env python3

import os
import signal
import time
import datetime
import logging
import shutil  # For disk space checking
import sounddevice as sd
from scipy.io.wavfile import write
import numpy as np

# --- Configuration Constants ---
# Audio recording parameters
RATE = 44100  # Sample rate (Hz)
CHANNELS = 1  # Mono recording
OUTPUT_DIR = '/var/lib/mic_recorder'
SEGMENT_DURATION_SECONDS = 30 * 60  # 30 minutes
CHUNK_DURATION_SECONDS = 5  # Record in 5-second chunks within a segment
PREFERRED_DEVICE_NAME_SUBSTRING = "" # e.g., "USB Mic", "HyperX", "" for auto-select

# Logging configuration
LOG_FILE = '/var/log/mic_recorder.log'
LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Disk space management
MIN_FREE_DISK_SPACE_MB = 200  # Minimum free disk space in MB to continue recording
DISK_CHECK_INTERVAL_SECONDS = 5 * 60 # How often to check disk space if initial check fails

# Retry and failure management
MAX_CONSECUTIVE_SEGMENT_FAILURES = 5 # Max number of segment failures before a long pause
RETRY_DELAY_ON_FAILURE_SECONDS = 10 # Shorter delay for general failures
LONG_PAUSE_ON_PERSISTENT_FAILURE_SECONDS = 15 * 60 # Longer pause if max failures reached
# --- End Configuration Constants ---

# Configure logging
logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    filename=LOG_FILE,
    filemode='a'
)
logger = logging.getLogger('mic_recorder')

# Ensure the output directory exists and is writable
try:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # Test writability
    test_file_path = os.path.join(OUTPUT_DIR, ".writable_test")
    with open(test_file_path, "w") as f:
        f.write("test")
    os.remove(test_file_path)
    logger.info(f"Output directory {OUTPUT_DIR} exists and is writable.")
except OSError as e:
    logger.critical(f"Failed to create or write to output directory {OUTPUT_DIR}: {e}. Exiting.")
    exit(1) # Exit if we can't create/write to the output directory

# Global flag to control recording
keep_recording = True
current_device_id = None # Store the currently used device ID

# Signal handler for graceful shutdown
def signal_handler(sig, frame):
    global keep_recording
    logger.info(f"Received signal {sig}. Attempting graceful shutdown...")
    keep_recording = False

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def get_timestamp():
    """Generate a timestamp for filenames"""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def get_free_disk_space_mb(directory):
    """Get free disk space in MB for the given directory's partition."""
    try:
        total, used, free = shutil.disk_usage(directory)
        free_mb = free // (1024 * 1024)
        return free_mb
    except Exception as e:
        logger.error(f"Could not check disk space for {directory}: {e}")
        return None # Indicate failure to check

def check_disk_space_sufficient():
    """Checks if there's enough disk space for an upcoming segment."""
    free_mb = get_free_disk_space_mb(OUTPUT_DIR)
    if free_mb is None:
        logger.warning("Could not verify disk space. Assuming sufficient for now.")
        return True # Proceed cautiously if check fails

    # Estimate segment size: duration * rate * channels * bytes_per_sample (2 for int16)
    estimated_segment_size_mb = (SEGMENT_DURATION_SECONDS * RATE * CHANNELS * 2) / (1024 * 1024)
    
    logger.info(f"Available disk space: {free_mb} MB. Estimated next segment size: {estimated_segment_size_mb:.2f} MB.")

    if free_mb < (estimated_segment_size_mb + MIN_FREE_DISK_SPACE_MB):
        logger.critical(
            f"Insufficient disk space. Free: {free_mb}MB, Estimated segment: {estimated_segment_size_mb:.2f}MB, Required minimum: {MIN_FREE_DISK_SPACE_MB}MB."
        )
        return False
    return True

def list_audio_devices_detailed():
    """List all available audio devices with details and return a list of dicts."""
    try:
        devices = sd.query_devices()
        logger.info("Available audio devices:")
        detailed_input_devices = []
        if not devices:
            logger.info("No audio devices found by sounddevice.")
            return []

        for i, device_info_raw in enumerate(devices):
            device_name = device_info_raw.get('name', 'Unknown Device')
            if isinstance(device_name, bytes):
                try:
                    device_name = device_name.decode('utf-8', 'replace')
                except Exception:
                    device_name = "Unreadable Device Name"
            
            host_api_index = device_info_raw.get('hostapi', -1)
            host_api_name = "N/A"
            if host_api_index != -1:
                try:
                    host_api_info = sd.query_hostapis(host_api_index)
                    host_api_name = host_api_info.get('name', 'N/A')
                except Exception as e:
                    logger.warning(f"Could not query host API for index {host_api_index}: {e}")


            device_log_info = (
                f"Device {i}: {device_name}, "
                f"Host API: {host_api_index}({host_api_name}), "
                f"Inputs: {device_info_raw.get('max_input_channels', 0)}, "
                f"Outputs: {device_info_raw.get('max_output_channels', 0)}, "
                f"Default SR: {device_info_raw.get('default_samplerate', 'N/A')}"
            )
            logger.info(device_log_info)
            
            if device_info_raw.get('max_input_channels', 0) > 0:
                detailed_input_devices.append({
                    'id': i, # The device index
                    'name': device_name,
                    'channels': device_info_raw['max_input_channels'],
                    'samplerate': device_info_raw['default_samplerate']
                })
        
        if not detailed_input_devices:
            logger.warning("No devices with input channels found.")
        return detailed_input_devices
    except Exception as e:
        logger.error(f"Error listing audio devices: {e}", exc_info=True)
        return []

def find_best_input_device():
    """Find the best available input device, considering preferred name."""
    global current_device_id
    try:
        all_input_devices = list_audio_devices_detailed()
        
        if not all_input_devices:
            logger.error("No input devices found after listing.")
            current_device_id = None
            return None

        # 1. Try preferred device name substring
        if PREFERRED_DEVICE_NAME_SUBSTRING:
            logger.info(f"Searching for preferred device containing: '{PREFERRED_DEVICE_NAME_SUBSTRING}'")
            for device in all_input_devices:
                if PREFERRED_DEVICE_NAME_SUBSTRING.lower() in device['name'].lower():
                    logger.info(f"Preferred device found: ID {device['id']} - {device['name']}")
                    current_device_id = device['id']
                    return device['id']
            logger.warning(f"Preferred device substring '{PREFERRED_DEVICE_NAME_SUBSTRING}' not found. Trying default.")

        # 2. Try to get the default input device
        try:
            default_device_info_raw = sd.query_devices(kind='input') # This is raw PortAudio info
            if default_device_info_raw and default_device_info_raw.get('max_input_channels',0) > 0 :
                # The 'index' in default_device_info_raw is the actual device ID
                idx = default_device_info_raw['index']
                
                # Find this device in our detailed list to log its name properly
                default_device_name = "Unknown (default)"
                for dev in all_input_devices:
                    if dev['id'] == idx:
                        default_device_name = dev['name']
                        break
                
                logger.info(f"Default input device identified: ID {idx} - {default_device_name}")
                current_device_id = idx
                return idx
            else:
                logger.warning("Default input device has no input channels or is not found by query_devices(kind='input').")
        except Exception as e:
            logger.warning(f"Could not determine default input device or it's unsuitable: {e}. Trying first available from list.")
        
        # 3. If no suitable default or preferred, use the first available input device from our list
        first_available = all_input_devices[0]
        logger.info(f"Using first available input device from list: ID {first_available['id']} - {first_available['name']}")
        current_device_id = first_available['id']
        return first_available['id']
        
    except Exception as e:
        logger.error(f"Error finding input device: {e}", exc_info=True)
        current_device_id = None
        return None

def record_segment(device_id_to_use, duration, output_path_final):
    """Record audio, save to temp file, then rename to final path."""
    if device_id_to_use is None:
        logger.error("Cannot record segment: No valid device ID provided.")
        return False
    
    output_path_temp = output_path_final + ".tmp"
        
    try:
        logger.info(f"Attempting to start recording to {output_path_temp} (final: {output_path_final}) using device ID {device_id_to_use}, Duration: {duration}s")
        
        num_chunks = int(duration / CHUNK_DURATION_SECONDS)
        if num_chunks == 0 and duration > 0: 
            num_chunks = 1
            current_chunk_duration = duration
        else:
            current_chunk_duration = CHUNK_DURATION_SECONDS
            if duration % CHUNK_DURATION_SECONDS != 0 and num_chunks > 0: # Ensure full duration
                 num_chunks +=1 # Add a partial chunk if duration is not a multiple of chunk_duration

        all_recorded_chunks = []
        segment_start_time = time.time()
        
        for i in range(num_chunks):
            if not keep_recording:
                logger.info("Recording stopped by signal during segment.")
                break
            
            # For the last chunk, it might be shorter if duration is not a multiple of CHUNK_DURATION_SECONDS
            actual_chunk_duration = current_chunk_duration
            if i == num_chunks -1 and duration % CHUNK_DURATION_SECONDS != 0:
                actual_chunk_duration = duration % CHUNK_DURATION_SECONDS
                if actual_chunk_duration == 0: # this happens if duration is a multiple
                    actual_chunk_duration = current_chunk_duration


            chunk_frames = int(actual_chunk_duration * RATE)
            if chunk_frames <= 0: # Avoid trying to record 0 frames
                continue

            try:
                logger.debug(f"Recording chunk {i+1}/{num_chunks} for {actual_chunk_duration:.2f}s...")
                recording_chunk_data = sd.rec(
                    frames=chunk_frames,
                    samplerate=RATE,
                    channels=CHANNELS,
                    device=device_id_to_use,
                    blocking=True,
                    dtype='float32'
                )
                all_recorded_chunks.append(recording_chunk_data)
                
                if i % (12 * (60 // CHUNK_DURATION_SECONDS if CHUNK_DURATION_SECONDS > 0 else 60)) == 0 or i == num_chunks - 1:
                    elapsed_time_in_segment = time.time() - segment_start_time
                    logger.info(f"Recorded chunk {i+1}/{num_chunks} (approx. {elapsed_time_in_segment/60:.1f} minutes into segment)")

            except sd.PortAudioError as pae:
                logger.error(f"PortAudioError during chunk {i+1} recording: {pae}. Device: {device_id_to_use}", exc_info=True)
                return False 
            except Exception as e:
                logger.error(f"Error recording chunk {i+1}: {e}. Device: {device_id_to_use}", exc_info=True)
                return False 
        
        actual_recorded_duration = time.time() - segment_start_time
        logger.info(f"Segment recording loop finished. Actual duration: {actual_recorded_duration:.2f}s. Combining {len(all_recorded_chunks)} chunks.")
        
        if not all_recorded_chunks:
            if keep_recording:
                 logger.error("No audio chunks were recorded for the segment, though recording was active.")
            # Clean up temp file if it exists and is empty or not created
            if os.path.exists(output_path_temp):
                try: os.remove(output_path_temp)
                except OSError: pass
            return False
            
        complete_recording = np.vstack(all_recorded_chunks)
        
        max_abs_val = np.max(np.abs(complete_recording))
        if max_abs_val > 0:
            scaling_factor = (32767 * 0.95) / max_abs_val
            normalized_recording = complete_recording * scaling_factor
        else:
            normalized_recording = complete_recording
        
        scaled_int16 = np.int16(normalized_recording)
        
        write(output_path_temp, RATE, scaled_int16) # Write to temp file
        logger.info(f"Successfully wrote segment to temporary file {output_path_temp}")

        # Atomically move temp file to final destination
        shutil.move(output_path_temp, output_path_final)
        logger.info(f"Successfully moved temporary file to final path {output_path_final}")
        return True
    
    except Exception as e:
        logger.error(f"Critical error during segment processing or saving: {e}", exc_info=True)
        # Clean up temp file if an error occurred after its creation
        if os.path.exists(output_path_temp):
            try:
                os.remove(output_path_temp)
                logger.info(f"Cleaned up temporary file {output_path_temp} due to error.")
            except OSError as ose:
                logger.error(f"Could not remove temporary file {output_path_temp} after error: {ose}")
        return False

def record_audio():
    global keep_recording, current_device_id
    consecutive_segment_failures = 0

    current_device_id = find_best_input_device()
    if current_device_id is None:
        logger.critical("No suitable input device found on startup. Will retry device search periodically.")
        time.sleep(RETRY_DELAY_ON_FAILURE_SECONDS)

    logger.info(f"Starting audio recording service. Device ID: {current_device_id if current_device_id is not None else 'Not yet found'}")
    
    while keep_recording:
        if current_device_id is None:
            logger.info("Attempting to find an audio input device...")
            current_device_id = find_best_input_device()
            if current_device_id is None:
                logger.error(f"Still no input device found. Waiting for {RETRY_DELAY_ON_FAILURE_SECONDS}s before retrying device search.")
                time.sleep(RETRY_DELAY_ON_FAILURE_SECONDS)
                continue 
            else:
                logger.info(f"Input device found: ID {current_device_id}. Proceeding with recording.")

        timestamp = get_timestamp()
        output_filename = f"recording_{timestamp}.wav"
        output_filepath_final = os.path.join(OUTPUT_DIR, output_filename)

        if not check_disk_space_sufficient():
            logger.critical(f"Disk space low. Pausing for {DISK_CHECK_INTERVAL_SECONDS}s before re-checking.")
            time.sleep(DISK_CHECK_INTERVAL_SECONDS)
            continue 

        success = record_segment(current_device_id, SEGMENT_DURATION_SECONDS, output_filepath_final)
        
        if not keep_recording:
            logger.info("Graceful stop signal received during or after segment. Exiting main loop.")
            break
            
        if success:
            consecutive_segment_failures = 0 
        else:
            logger.warning(f"Segment recording to {output_filepath_final} failed.")
            consecutive_segment_failures += 1
            
            logger.info("Attempting to re-initialize audio device due to segment failure.")
            current_device_id = find_best_input_device() 
            if current_device_id is None:
                 logger.error("Failed to re-initialize audio device. Will retry device search in main loop.")

            if consecutive_segment_failures >= MAX_CONSECUTIVE_SEGMENT_FAILURES:
                logger.critical(
                    f"Reached maximum consecutive segment failures ({MAX_CONSECUTIVE_SEGMENT_FAILURES}). "
                    f"Pausing for {LONG_PAUSE_ON_PERSISTENT_FAILURE_SECONDS}s."
                )
                time.sleep(LONG_PAUSE_ON_PERSISTENT_FAILURE_SECONDS)
                consecutive_segment_failures = 0 
            else:
                logger.info(f"Waiting for {RETRY_DELAY_ON_FAILURE_SECONDS}s before trying next segment.")
                time.sleep(RETRY_DELAY_ON_FAILURE_SECONDS)
                
    logger.info("Audio recording service main loop has ended.")

if __name__ == "__main__":
    try:
        logger.info("Mic Recorder Service started.")
        record_audio()
    except Exception as e:
        logger.critical(f"An unhandled critical error occurred in __main__: {e}", exc_info=True)
    finally:
        logger.info("Mic Recorder Service stopped.")
