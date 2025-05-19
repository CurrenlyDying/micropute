#!/bin/bash

# Exit on error
set -e

echo "Installing mic_recorder service..."

# Install required system packages
echo "Installing system dependencies..."
apt-get update
apt-get install -y python3 python3-venv python3-full portaudio19-dev libasound2-dev

# Create directories
echo "Setting up directories..."
mkdir -p /var/lib/mic_recorder
chmod 777 /var/lib/mic_recorder
mkdir -p /var/log
touch /var/log/mic_recorder.log
chmod 666 /var/log/mic_recorder.log
INSTALL_DIR="/opt/mic_recorder"
mkdir -p $INSTALL_DIR

# Copy application files
echo "Copying application files..."
cp mic_recorder.py $INSTALL_DIR/

# Create virtual environment and install dependencies
echo "Creating virtual environment and installing Python dependencies..."
python3 -m venv $INSTALL_DIR/venv
$INSTALL_DIR/venv/bin/pip install sounddevice scipy numpy

# Create the systemd service file
echo "Creating systemd service file..."
cat > /etc/systemd/system/mic_recorder.service << EOF
[Unit]
Description=Microphone Audio Recording Service
After=network.target

[Service]
Type=simple
User=root
Group=root
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/mic_recorder.py
Restart=always
RestartSec=5
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=mic_recorder

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
echo "Enabling service..."
systemctl daemon-reload
systemctl enable mic_recorder.service

echo "Installation complete!"
echo "To start the service, run: sudo systemctl start mic_recorder"
echo "To check the status, run: sudo systemctl status mic_recorder"
echo "Audio will be saved to: /var/lib/mic_recorder"
echo "Logs are available at: /var/log/mic_recorder.log"

# Print detected audio devices for diagnostics
echo ""
echo "Detected audio devices:"
$INSTALL_DIR/venv/bin/python -c "import sounddevice as sd; print(sd.query_devices())"
echo ""
echo "The service will automatically use the first available input device when started." 