#!/bin/bash

# Exit on error
set -e

echo "Uninstalling mic_recorder service..."

# Stop and disable the service
echo "Stopping and disabling service..."
systemctl stop mic_recorder.service || echo "Service already stopped"
systemctl disable mic_recorder.service || echo "Service already disabled"

# Remove service file
echo "Removing service file..."
rm -f /etc/systemd/system/mic_recorder.service

# Reload systemd
systemctl daemon-reload

# Remove installation directory
echo "Removing application files..."
rm -rf /opt/mic_recorder

# Optionally ask about recorded data
echo "Do you want to remove recorded audio files in /var/lib/mic_recorder? (y/N)"
read -r response
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo "Removing recorded audio files..."
    rm -rf /var/lib/mic_recorder
else
    echo "Keeping recorded audio files in /var/lib/mic_recorder"
fi

# Optionally ask about logs
echo "Do you want to remove log files? (y/N)"
read -r response
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo "Removing log file..."
    rm -f /var/log/mic_recorder.log
else
    echo "Keeping log file at /var/log/mic_recorder.log"
fi

echo "Uninstallation complete!" 