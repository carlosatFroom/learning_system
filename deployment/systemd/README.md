# Systemd Service Installation

## Installation Instructions

1. **Update the service file paths:**
   - Replace `/path/to/learning_system` with the actual deployment path
   - Update `User` and `Group` to match your server's user (commonly `www-data`, `nginx`, or your deployment user)

2. **Create log directory:**
   ```bash
   sudo mkdir -p /var/log/learning-system
   sudo chown <your-user>:<your-group> /var/log/learning-system
   ```

3. **Copy the service file:**
   ```bash
   sudo cp deployment/systemd/learning-system.service /etc/systemd/system/
   ```

4. **Reload systemd and enable the service:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable learning-system.service
   sudo systemctl start learning-system.service
   ```

5. **Check service status:**
   ```bash
   sudo systemctl status learning-system.service
   ```

## Service Management Commands

- **Start:** `sudo systemctl start learning-system.service`
- **Stop:** `sudo systemctl stop learning-system.service`
- **Restart:** `sudo systemctl restart learning-system.service`
- **View logs:** `sudo journalctl -u learning-system.service -f`
- **View log files:**
  - Access: `/var/log/learning-system/access.log`
  - Errors: `/var/log/learning-system/error.log`

## Notes

- The `--reload` flag has been removed for production use (it's only for development)
- The service will automatically restart if it crashes
- Logs are written to `/var/log/learning-system/`
- If you need the reload functionality in production, add `--reload` to the ExecStart line (not recommended)
