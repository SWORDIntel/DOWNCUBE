# Roundcube Email Downloader - Setup Guide

## Features

### 🎯 TUI Framework
- Built with **Textual** - modern, reactive TUI framework
- Beautiful interface with tabs, modals, and progress indicators
- Keyboard shortcuts for quick navigation

### 📧 Email Management
- **Multi-account support** - Add and manage multiple Roundcube accounts
- **Folder browser** - Navigate your email folder structure
- **Email preview** - View email content before downloading
- **Search/filter** - Search by subject, sender, or all fields
- **Batch selection** - Select/deselect all emails easily

### 💾 Export Formats
- **EML files** - Individual email files
- **MBOX format** - Mailbox archives
- **JSON export** - Structured data with email bodies
- **CSV export** - Spreadsheet-friendly format
- **Folder preservation** - Maintain original folder structure

### 🚀 Performance
- **Progress tracking** - Real-time download progress
- **Concurrent downloads** - Configurable parallel processing
- **Skip existing** - Avoid re-downloading files
- **Error handling** - Robust error recovery

## Installation

### 1. Create Virtual Environment
```bash
python -m venv roundcube_env
source roundcube_env/bin/activate  # On Windows: roundcube_env\Scripts\activate
```

### 2. Install Dependencies
```bash
pip install textual==0.47.1
pip install textual[dev]  # Optional: for development tools
```

### 3. Save the Script
Save the main script as `roundcube_downloader.py`

### 4. Make Executable (Linux/Mac)
```bash
chmod +x roundcube_downloader.py
```

## Usage

### Starting the Application
```bash
python roundcube_downloader.py
```

### Keyboard Shortcuts
- `a` - Add new account
- `r` - Refresh current folder
- `d` - Download selected emails
- `p` - Preview selected email
- `q` - Quit application
- `Tab` - Switch between tabs
- `↑↓` - Navigate lists/tables
- `Space` - Select/deselect items

### Workflow

1. **Add Account**
   - Press `a` or click "Add Account"
   - Enter your Roundcube server details:
     - Account name (for identification)
     - IMAP server address
     - Username/email
     - Password
     - Port (default: 993 for SSL)
     - SSL/TLS option

2. **Connect**
   - Select account from list
   - Click "Connect" button
   - Folders will load automatically

3. **Browse Emails**
   - Click on folders in the tree
   - Emails load in the table
   - Click rows to select/deselect

4. **Search** (Optional)
   - Enter search terms
   - Select search field (All/Subject/From)
   - Click "Search" or press Enter

5. **Preview** (Optional)
   - Select an email
   - Press `p` or click "Preview"
   - View content in modal window

6. **Download**
   - Select emails (click rows or "Select All")
   - Choose export formats (EML/MBOX/JSON/CSV)
   - Press `d` or click "Download Selected"
   - Monitor progress bar

### Settings

In the Settings tab, you can configure:
- **Download directory** - Where to save emails
- **Concurrent downloads** - Number of parallel downloads
- **Preserve folder structure** - Maintain server folder hierarchy
- **Skip existing files** - Avoid re-downloading

## File Formats

### EML Format
- One file per email
- Standard email format
- Can be opened in most email clients
- Filename: `{UID}_{Subject}.eml`

### MBOX Format
- One file per folder
- Contains all emails from that folder
- Compatible with Thunderbird, Apple Mail, etc.
- Filename: `{FolderName}.mbox`

### JSON Format
- All selected emails in one file
- Includes full email bodies
- Structured data for processing
- Filename: `emails.json`

### CSV Format
- Spreadsheet-friendly format
- Includes metadata (no bodies)
- Easy to import into Excel/Google Sheets
- Filename: `emails.csv`

## Advanced Features

### Account Persistence
- Accounts are saved to `accounts.pkl`
- Passwords are stored locally (consider security implications)
- Remove this file to reset all accounts

### Folder Structure
With "Preserve folder structure" enabled:
```
email_downloads/
├── INBOX/
│   ├── 123_Meeting_Notes.eml
│   └── 124_Project_Update.eml
├── Sent/
│   └── 125_Re_Meeting.eml
└── Projects/
    └── TeamA/
        └── 126_Sprint_Review.eml
```

### Search Capabilities
- **All** - Search in subject and sender
- **Subject** - Search only in subject lines
- **From** - Search only in sender addresses
- **Body** - Full-text search (requires fetching all emails)

## Troubleshooting

### Connection Issues
- Verify server address and port
- Check SSL/TLS settings
- Some servers use port 143 for non-SSL
- Ensure IMAP is enabled on your account

### Performance
- Large folders may take time to load
- Adjust concurrent downloads for your connection
- Use search to filter before downloading

### Character Encoding
- The app handles UTF-8 encoding
- Special characters in subjects are sanitized for filenames
- Email bodies preserve original encoding

## Security Notes

⚠️ **Important Security Considerations:**
- Passwords are stored locally in `accounts.pkl`
- Use this tool only on trusted computers
- Consider using app-specific passwords
- Delete `accounts.pkl` when done

## Requirements

- Python 3.8+
- textual>=0.47.1
- No additional system dependencies
- Works on Windows, macOS, and Linux

## Tips

1. **Large Downloads**: For thousands of emails, download in batches by folder
2. **Backup**: The tool doesn't delete emails from server
3. **Resume**: Use "Skip existing files" to resume interrupted downloads
4. **Multiple Formats**: You can export to multiple formats simultaneously
5. **Filtering**: Use search before selecting to narrow down emails

## Future Enhancements

Possible additions:
- OAuth2 authentication support
- Attachment extraction
- Email threading visualization
- Advanced search with date ranges
- Export to PDF format
- Scheduled backups
- Cloud storage integration
