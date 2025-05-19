#!/bin/bash

# Exit on error
set -e

echo "Installing mic_recorder service..."

# Install required packages
echo "Installing dependencies..."
apt-get update
apt-get install -y python3 python3-pip portaudio19-dev

# Install Python dependencies
echo "Installing Python packages..."
pip3 install pyaudio

# Create required directories
echo "Setting up directories..."
mkdir -p /var/lib/mic_recorder
mkdir -p /var/log

# Copy files to their locations
echo "Installing application files..."
cp mic_recorder.py /usr/local/bin/
chmod +x /usr/local/bin/mic_recorder.py
cp mic_recorder.service /etc/systemd/system/

# Reload systemd and enable service
echo "Enabling service..."
systemctl daemon-reload
systemctl enable mic_recorder.service

echo "Installation complete!"
echo "To start the service, run: sudo systemctl start mic_recorder"
echo "To check the status, run: sudo systemctl status mic_recorder"
echo "Audio will be saved to: /var/lib/mic_recorder"
echo "Logs are available at: /var/log/mic_recorder.log" 