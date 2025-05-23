#!/bin/bash

# Exit on any error
set -e

# --- Configuration ---
INSTALL_DIR="/opt/mic_recorder"
VENV_DIR="$INSTALL_DIR/venv"
SERVICE_NAME="mic_recorder"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PYTHON_EXEC="python3" # Can be changed to python3.x if needed
MIN_PYTHON_VERSION="3.7" # Minimum required Python version

# Log file for this installation script
INSTALL_LOG_FILE="/tmp/${SERVICE_NAME}_install.log"

# --- Helper Functions ---
log_info() {
    echo "[INFO] $1" | tee -a "$INSTALL_LOG_FILE"
}

log_error() {
    echo "[ERROR] $1" | tee -a "$INSTALL_LOG_FILE" >&2
}

log_warning() {
    echo "[WARN] $1" | tee -a "$INSTALL_LOG_FILE"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log_error "This script must be run as root. Please use sudo."
        exit 1
    fi
}

check_python_version() {
    CURRENT_PYTHON_VERSION=$($PYTHON_EXEC -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    if [ "$(printf '%s\n' "$MIN_PYTHON_VERSION" "$CURRENT_PYTHON_VERSION" | sort -V | head -n1)" != "$MIN_PYTHON_VERSION" ]; then
        log_error "Python version $CURRENT_PYTHON_VERSION is less than the required minimum $MIN_PYTHON_VERSION."
        log_error "Please install Python $MIN_PYTHON_VERSION or higher."
        exit 1
    fi
    log_info "Python version $CURRENT_PYTHON_VERSION meets requirements."
}

install_dependencies() {
    log_info "Updating package lists..."
    apt-get update -y >> "$INSTALL_LOG_FILE" 2>&1 || { log_error "Failed to update package lists."; exit 1; }

    log_info "Installing system dependencies: $PYTHON_EXEC python3-venv python3-pip portaudio19-dev libasound2-dev..."
    # Added python3-pip explicitly as venv might not always pull it in older systems
    apt-get install -y $PYTHON_EXEC python3-venv python3-pip portaudio19-dev libasound2-dev >> "$INSTALL_LOG_FILE" 2>&1 || { log_error "Failed to install system dependencies."; exit 1; }
    log_info "System dependencies installed successfully."
}

setup_directories() {
    log_info "Setting up directories..."
    mkdir -p "$INSTALL_DIR" || { log_error "Failed to create installation directory $INSTALL_DIR."; exit 1; }
    mkdir -p "/var/lib/${SERVICE_NAME}" || { log_error "Failed to create data directory /var/lib/${SERVICE_NAME}."; exit 1; }
    chmod 777 "/var/lib/${SERVICE_NAME}" # Permissive for simplicity, consider more restrictive if needed
    
    # Log directory and file
    mkdir -p "/var/log"
    touch "/var/log/${SERVICE_NAME}.log" || { log_error "Failed to create log file /var/log/${SERVICE_NAME}.log."; exit 1; }
    chmod 666 "/var/log/${SERVICE_NAME}.log" # Permissive for the service to write
    log_info "Directories set up successfully."
}

copy_application_files() {
    log_info "Copying application files..."
    if [ ! -f "mic_recorder.py" ]; then
        log_error "mic_recorder.py not found in the current directory. Make sure you are in the correct directory."
        exit 1
    fi
    cp "mic_recorder.py" "$INSTALL_DIR/" || { log_error "Failed to copy mic_recorder.py."; exit 1; }
    log_info "Application files copied."
}

setup_virtual_environment() {
    log_info "Creating virtual environment in $VENV_DIR..."
    if [ -d "$VENV_DIR" ]; then
        log_warning "Virtual environment directory $VENV_DIR already exists. Re-creating."
        rm -rf "$VENV_DIR"
    fi
    $PYTHON_EXEC -m venv "$VENV_DIR" >> "$INSTALL_LOG_FILE" 2>&1 || { log_error "Failed to create virtual environment."; exit 1; }
    
    log_info "Installing Python dependencies (sounddevice, scipy, numpy) into virtual environment..."
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"
    pip install --no-cache-dir sounddevice scipy numpy >> "$INSTALL_LOG_FILE" 2>&1 || { log_error "Failed to install Python dependencies."; deactivate; exit 1; }
    deactivate
    log_info "Python dependencies installed successfully."
}

create_systemd_service() {
    log_info "Creating systemd service file at $SERVICE_FILE..."
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Microphone Audio Recording Service (${SERVICE_NAME})
After=network.target sound.target

[Service]
Type=simple
User=root  # Or a dedicated non-root user if preferred, ensure permissions align
Group=root # Or a dedicated non-root user if preferred
ExecStart=${VENV_DIR}/bin/python ${INSTALL_DIR}/mic_recorder.py
Restart=always
RestartSec=10 # Increased restart delay
StandardOutput=append:/var/log/${SERVICE_NAME}.log
StandardError=append:/var/log/${SERVICE_NAME}.log
SyslogIdentifier=${SERVICE_NAME}

# Optional: Add resource limits if needed
# CPUQuota=50%
# MemoryMax=512M

[Install]
WantedBy=multi-user.target
EOF
    chmod 644 "$SERVICE_FILE"
    log_info "Systemd service file created."
}

enable_service() {
    log_info "Reloading systemd daemon..."
    systemctl daemon-reload >> "$INSTALL_LOG_FILE" 2>&1 || { log_error "Failed to reload systemd daemon."; exit 1; }
    
    log_info "Enabling ${SERVICE_NAME} service to start on boot..."
    systemctl enable "${SERVICE_NAME}.service" >> "$INSTALL_LOG_FILE" 2>&1 || { log_error "Failed to enable ${SERVICE_NAME} service."; exit 1; }
    log_info "${SERVICE_NAME} service enabled."
}

# --- Main Script ---
main() {
    # Clear previous install log
    >"$INSTALL_LOG_FILE"
    log_info "Starting mic_recorder service installation..."
    log_info "Installation log will be saved to $INSTALL_LOG_FILE"

    check_root

    log_info "Checking for required commands..."
    for cmd in $PYTHON_EXEC apt-get systemctl; do
        if ! command_exists "$cmd"; then
            log_error "Required command '$cmd' not found. Please install it and try again."
            exit 1
        fi
    done
    log_info "All basic commands found."

    check_python_version
    install_dependencies
    setup_directories
    copy_application_files
    setup_virtual_environment
    create_systemd_service
    systemctl disable "${SERVICE_NAME}.service"
    
    log_info ""
    log_info "Installation complete!"
    log_info "---------------------------------------------------------------------"
    log_info "The ${SERVICE_NAME} service has been installed and enabled."
    log_info "Audio will be saved to: /var/lib/${SERVICE_NAME}"
    log_info "Logs for the service are available at: /var/log/${SERVICE_NAME}.log"
    log_info "Installation script logs are at: ${INSTALL_LOG_FILE}"
    log_info ""
    log_info "To start the service now, run: sudo systemctl start ${SERVICE_NAME}"
    log_info "To check the status, run:      sudo systemctl status ${SERVICE_NAME}"
    log_info "To view live logs, run:        sudo tail -f /var/log/${SERVICE_NAME}.log"
    log_info "---------------------------------------------------------------------"
    
    echo ""
    echo "Attempting to list audio devices for initial diagnostics (using the installed venv):"
    if ! "$VENV_DIR/bin/python" -c "import sounddevice as sd; print('--- Detected Sound Devices ---'); print(sd.query_devices()); print('--- Default Input Device ---'); print(sd.query_devices(kind='input'))" 2>/dev/null; then
        log_warning "Could not list audio devices automatically. This might indicate an issue with sounddevice or PortAudio setup."
        log_warning "Please check logs and ensure audio hardware is correctly configured."
    fi
    echo ""
    log_info "Installation script finished."
}

# Run main function
main

exit 0
