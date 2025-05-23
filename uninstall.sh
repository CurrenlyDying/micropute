#!/bin/bash

# Exit on any error
set -e

# --- Configuration ---
INSTALL_DIR="/opt/mic_recorder"
SERVICE_NAME="mic_recorder"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
DATA_DIR="/var/lib/${SERVICE_NAME}"
LOG_FILE_PATH="/var/log/${SERVICE_NAME}.log"

# Log file for this uninstallation script
UNINSTALL_LOG_FILE="/tmp/${SERVICE_NAME}_uninstall.log"

# --- Helper Functions ---
log_info() {
    echo "[INFO] $1" | tee -a "$UNINSTALL_LOG_FILE"
}

log_error() {
    echo "[ERROR] $1" | tee -a "$UNINSTALL_LOG_FILE" >&2
}

log_warning() {
    echo "[WARN] $1" | tee -a "$UNINSTALL_LOG_FILE"
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

service_exists() {
    systemctl list-units --full -all | grep -q "^${SERVICE_NAME}.service"
}

stop_and_disable_service() {
    log_info "Stopping and disabling ${SERVICE_NAME} service..."
    if service_exists; then
        log_info "Service ${SERVICE_NAME} found. Attempting to stop..."
        systemctl stop "${SERVICE_NAME}.service" >> "$UNINSTALL_LOG_FILE" 2>&1 || log_warning "Failed to stop ${SERVICE_NAME} service (it might not be running)."
        
        log_info "Attempting to disable ${SERVICE_NAME} service..."
        systemctl disable "${SERVICE_NAME}.service" >> "$UNINSTALL_LOG_FILE" 2>&1 || log_warning "Failed to disable ${SERVICE_NAME} service (it might already be disabled)."
    else
        log_warning "Service ${SERVICE_NAME}.service does not appear to be installed or was already removed."
    fi
}

remove_service_file() {
    log_info "Removing systemd service file..."
    if [ -f "$SERVICE_FILE" ]; then
        rm -f "$SERVICE_FILE" || { log_error "Failed to remove service file $SERVICE_FILE."; exit 1; }
        log_info "Service file $SERVICE_FILE removed."
        
        log_info "Reloading systemd daemon..."
        systemctl daemon-reload >> "$UNINSTALL_LOG_FILE" 2>&1 || { log_error "Failed to reload systemd daemon."; exit 1; }
        log_info "Systemd daemon reloaded."
    else
        log_warning "Service file $SERVICE_FILE not found."
    fi
}

remove_application_files() {
    log_info "Removing application installation directory: $INSTALL_DIR..."
    if [ -d "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR" || { log_error "Failed to remove directory $INSTALL_DIR."; exit 1; }
        log_info "Application directory $INSTALL_DIR removed."
    else
        log_warning "Application directory $INSTALL_DIR not found."
    fi
}

prompt_remove_data() {
    if [ -d "$DATA_DIR" ]; then
        echo ""
        read -r -p "Do you want to remove recorded audio files in $DATA_DIR? (This is irreversible) [y/N]: " response
        echo "$response" >> "$UNINSTALL_LOG_FILE" # Log the response
        if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
            log_info "User chose to remove data directory: $DATA_DIR."
            rm -rf "$DATA_DIR" || { log_error "Failed to remove data directory $DATA_DIR."; exit 1; }
            log_info "Data directory $DATA_DIR removed."
        else
            log_info "User chose to keep data directory: $DATA_DIR."
        fi
    else
        log_info "Data directory $DATA_DIR not found. Nothing to remove."
    fi
}

prompt_remove_logs() {
    if [ -f "$LOG_FILE_PATH" ]; then
        echo ""
        read -r -p "Do you want to remove the service log file $LOG_FILE_PATH? [y/N]: " response
        echo "$response" >> "$UNINSTALL_LOG_FILE" # Log the response
        if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
            log_info "User chose to remove log file: $LOG_FILE_PATH."
            rm -f "$LOG_FILE_PATH" || { log_error "Failed to remove log file $LOG_FILE_PATH."; exit 1; }
            log_info "Log file $LOG_FILE_PATH removed."
        else
            log_info "User chose to keep log file: $LOG_FILE_PATH."
        fi
    else
        log_info "Service log file $LOG_FILE_PATH not found. Nothing to remove."
    fi
}

# --- Main Script ---
main() {
    # Clear previous uninstall log
    >"$UNINSTALL_LOG_FILE"
    log_info "Starting mic_recorder service uninstallation..."
    log_info "Uninstallation log will be saved to $UNINSTALL_LOG_FILE"

    check_root

    log_info "Checking for required commands..."
    for cmd in systemctl rm; do # Add other commands if needed
        if ! command_exists "$cmd"; then
            log_error "Required command '$cmd' not found. Please install it and try again."
            exit 1
        fi
    done
    log_info "All basic commands found."

    stop_and_disable_service
    remove_service_file
    remove_application_files
    
    # Prompts should come after critical parts are done or if they are optional
    prompt_remove_data
    prompt_remove_logs

    log_info ""
    log_info "Mic Recorder uninstallation process complete."
    log_info "---------------------------------------------------------------------"
    log_info "If you chose not to remove them, data may still exist in: $DATA_DIR"
    log_info "If you chose not to remove it, logs may still exist at: $LOG_FILE_PATH"
    log_info "Uninstallation script logs are at: ${UNINSTALL_LOG_FILE}"
    log_info ""
    log_info "Note: The following packages were installed as dependencies by the installer"
    log_info "and can be removed manually if no longer needed by other applications:"
    log_info "- python3 (if solely installed for this)"
    log_info "- python3-venv"
    log_info "- python3-pip"
    log_info "- portaudio19-dev"
    log_info "- libasound2-dev"
    log_info ""
    log_info "To remove them, you might run: sudo apt-get autoremove"
    log_info "Or specifically: sudo apt-get remove python3-venv python3-pip portaudio19-dev libasound2-dev"
    log_info "(Be cautious with 'autoremove' or removing 'python3' itself if other applications depend on them.)"
    log_info "---------------------------------------------------------------------"
    log_info "Uninstallation script finished."
}

# Run main function
main

exit 0
