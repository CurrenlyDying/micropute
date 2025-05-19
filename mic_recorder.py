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
SEGMENT_DURATION_SECONDS = 30 * 60  # 30 minutes

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

def record_audio():
    """Main recording function, creates a new file every SEGMENT_DURATION_SECONDS."""
    p = None
    stream = None
    current_wf = None
    current_wav_file_path = None # Stores the path of the currently open WAV file

    try:
        p = pyaudio.PyAudio()
        logger.info("Starting audio recording service.")

        # Open stream once at the beginning
        stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)
        logger.info("Audio stream opened successfully.")

        # Outer loop: continues as long as keep_recording is True, creating new segments
        while keep_recording:
            timestamp = get_timestamp()
            current_wav_file_path = os.path.join(OUTPUT_DIR, f"recording_{timestamp}.wav")
            
            segment_frames = [] # Temporary store for current segment's frames, if needed for retry, but wave module writes directly
            
            try: # Try block for operations related to a single segment file
                current_wf = wave.open(current_wav_file_path, 'wb')
                current_wf.setnchannels(CHANNELS)
                current_wf.setsampwidth(p.get_sample_size(FORMAT))
                current_wf.setframerate(RATE)
                
                logger.info(f"Recording new segment to {current_wav_file_path}")
                segment_start_time = time.time()
                
                # Inner loop: records data for the current segment
                while keep_recording:
                    try:
                        data = stream.read(CHUNK, exception_on_overflow=False)
                        current_wf.writeframes(data)
                    except IOError as e:
                        # This error type can occur if the stream is closed or encounters a serious issue.
                        logger.error(f"Stream read IOError while recording to {current_wav_file_path}: {e}. Attempting to stop.", exc_info=True)
                        global keep_recording # Modifying global
                        keep_recording = False # Signal to stop all recording activities
                        # Re-raise to be caught by the segment's exception handler, which will close the current file.
                        raise
                    except Exception as e_read:
                        logger.error(f"Unexpected error during stream.read() for {current_wav_file_path}: {e_read}", exc_info=True)
                        # Depending on the error, might want to stop or try to continue with a new segment.
                        # For now, let this error propagate to the segment error handler.
                        raise


                    # Check if segment duration is reached
                    if time.time() - segment_start_time >= SEGMENT_DURATION_SECONDS:
                        logger.info(f"Segment duration ({SEGMENT_DURATION_SECONDS // 60} min) reached for {current_wav_file_path}.")
                        break # Break inner loop to close this segment and start a new one
                
                # End of inner loop (either due to segment duration or keep_recording becoming False)

            except Exception as e_segment:
                # This catches errors from wave.open, stream.read (if re-raised), or writeframes.
                logger.error(f"Error during processing of segment {current_wav_file_path}: {e_segment}", exc_info=True)
                # If keep_recording became false due to this error, the outer loop will terminate.
            finally:
                if current_wf:
                    try:
                        current_wf.close()
                        logger.info(f"Segment successfully saved and closed: {current_wav_file_path}")
                    except Exception as e_close:
                        logger.error(f"Error closing wave file {current_wav_file_path}: {e_close}", exc_info=True)
                    current_wf = None # Ensure it's reset
                    current_wav_file_path = None # Reset path after closing
            
            if not keep_recording:
                logger.info("Stop signal received or critical error occurred, exiting main recording loop.")
                break # Break outer loop

    except pyaudio.PaError as pa_err:
        logger.critical(f"PyAudio error: {pa_err}. This often means an issue with the audio device.", exc_info=True)
        # PyAudio might not have initialized, so p might be None or p.terminate() might fail.
    except Exception as e_main:
        logger.critical(f"A critical error occurred in the main recording function: {e_main}", exc_info=True)
    finally:
        logger.info("Cleaning up resources...")

        # Ensure the last wave file is closed if it's still open due to an unhandled exit path
        # (though the segment's finally should have handled it)
        if current_wf is not None: # Check if current_wf was assigned and not reset
            logger.warning(f"Main finally: current_wf for {current_wav_file_path or 'unknown segment'} was not None. Attempting to close.")
            try:
                # Check if it has a close method and isn't already marked closed by wave module internals
                if hasattr(current_wf, 'close') and not getattr(current_wf, '_is_closed', True): # _is_closed is internal
                    current_wf.close()
                    logger.info(f"Closed lingering wave file {current_wav_file_path or 'unknown segment'} in main finally.")
            except Exception as e_final_wf_close:
                logger.error(f"Error during final attempt to close wave file {current_wav_file_path or 'unknown segment'}: {e_final_wf_close}")

        if stream is not None:
            try:
                if stream.is_active():
                    logger.info("Stopping audio stream.")
                    stream.stop_stream()
                logger.info("Closing audio stream.")
                stream.close()
            except Exception as e_stream_cleanup:
                logger.error(f"Error during stream cleanup: {e_stream_cleanup}", exc_info=True)
        
        if p is not None:
            try:
                logger.info("Terminating PyAudio instance.")
                p.terminate()
            except Exception as e_pyaudio_cleanup:
                logger.error(f"Error during PyAudio termination: {e_pyaudio_cleanup}", exc_info=True)
        
        logger.info("Recording service stopped.")

if __name__ == "__main__":
    record_audio()