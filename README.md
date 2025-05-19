# MicRecorder

A Linux service that continuously records audio from the microphone and saves it as a single WAV file.

## Features

- Runs as a systemd service in the background
- Records audio from the system microphone
- Saves audio as a single WAV file for the entire recording session
- Handles service stops gracefully without corrupting files
- Automatically restarts if crashed

## Requirements

- Linux system with systemd
- Python 3
- Root access for service installation

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/CurrenlyDying/micropute
   cd micropute
   ```

2. Run the installer script as root:
   ```
   sudo bash install.sh
   ```

3. Start the service:
   ```
   sudo systemctl start mic_recorder
   ```

## Usage

The service runs in the background and requires no interaction:

- Start recording: `sudo systemctl start mic_recorder`
- Stop recording: `sudo systemctl stop mic_recorder`
- Check status: `sudo systemctl status mic_recorder`
- Enable at boot: `sudo systemctl enable mic_recorder` (done by installer)
- Disable at boot: `sudo systemctl disable mic_recorder`

When you start the service, it begins recording. When you stop the service, it completes the WAV file and closes it properly.

## Configuration

Edit `/usr/local/bin/mic_recorder.py` to change settings:

- `CHANNELS`: Number of audio channels (1 for mono, 2 for stereo)
- `RATE`: Sample rate in Hz (default: 44100)
- `OUTPUT_DIR`: Where to save recordings (default: `/var/lib/mic_recorder`)

After changing, restart the service:
```
sudo systemctl restart mic_recorder
```

## Logs

Service logs are stored in `/var/log/mic_recorder.log` and can be viewed with:
```
sudo tail -f /var/log/mic_recorder.log
```

## Uninstallation

To remove the service:
```
sudo systemctl stop mic_recorder
sudo systemctl disable mic_recorder
sudo rm /etc/systemd/system/mic_recorder.service
sudo rm /usr/local/bin/mic_recorder.py
sudo systemctl daemon-reload
```

## Recordings

Audio recordings are saved to `/var/lib/mic_recorder/` with filenames in the format `recording_YYYYMMDD_HHMMSS.wav`. Each file represents a complete recording session from service start to service stop. 