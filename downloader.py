#!/usr/bin/env python3
"""
Roundcube Email Downloader - A comprehensive TUI for downloading emails
Supports multiple accounts, various export formats, and advanced features
"""

import os
import json
import csv
import email
import imaplib
import mailbox
import asyncio
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
import pickle

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, Tree, Label, Input, Button, DataTable,
    ProgressBar, TextArea, Select, Checkbox, TabbedContent, TabPane,
    Static, ListView, ListItem, DirectoryTree
)
from textual.screen import Screen, ModalScreen
from textual.reactive import reactive
from textual.message import Message

# Data structures
@dataclass
class Account:
    name: str
    server: str
    username: str
    password: str
    port: int = 993
    use_ssl: bool = True

@dataclass
class EmailMessage:
    uid: str
    subject: str
    sender: str
    date: str
    size: int
    folder: str
    raw_email: Optional[bytes] = None
    
class AddAccountModal(ModalScreen[Account]):
    """Modal screen for adding new email accounts"""
    
    def compose(self) -> ComposeResult:
        yield Container(
            Label("Add Email Account", id="modal-title"),
            Input(placeholder="Account Name", id="account-name"),
            Input(placeholder="IMAP Server", id="server"),
            Input(placeholder="Username/Email", id="username"),
            Input(placeholder="Password", password=True, id="password"),
            Input(placeholder="Port (993)", id="port", value="993"),
            Checkbox("Use SSL/TLS", value=True, id="use-ssl"),
            Horizontal(
                Button("Add", variant="primary", id="add"),
                Button("Cancel", variant="error", id="cancel"),
                id="button-container"
            ),
            id="modal-container"
        )
    
    @on(Button.Pressed, "#add")
    def add_account(self) -> None:
        name = self.query_one("#account-name", Input).value
        server = self.query_one("#server", Input).value
        username = self.query_one("#username", Input).value
        password = self.query_one("#password", Input).value
        port = int(self.query_one("#port", Input).value or "993")
        use_ssl = self.query_one("#use-ssl", Checkbox).value
        
        if all([name, server, username, password]):
            account = Account(name, server, username, password, port, use_ssl)
            self.dismiss(account)
    
    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None:
        self.dismiss(None)

class EmailPreviewModal(ModalScreen[None]):
    """Modal for previewing email content"""
    
    def __init__(self, email_msg: EmailMessage, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.email_msg = email_msg
    
    def compose(self) -> ComposeResult:
        yield Container(
            Label(f"Subject: {self.email_msg.subject}", id="preview-subject"),
            Label(f"From: {self.email_msg.sender}", id="preview-from"),
            Label(f"Date: {self.email_msg.date}", id="preview-date"),
            TextArea(id="preview-content", read_only=True),
            Button("Close", variant="primary", id="close"),
            id="preview-container"
        )
    
    async def on_mount(self) -> None:
        if self.email_msg.raw_email:
            try:
                msg = email.message_from_bytes(self.email_msg.raw_email)
                body = self.extract_body(msg)
                self.query_one("#preview-content", TextArea).text = body
            except Exception as e:
                self.query_one("#preview-content", TextArea).text = f"Error parsing email: {str(e)}"
    
    def extract_body(self, msg) -> str:
        """Extract email body from message"""
        body_parts = []
        
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        body_parts.append(part.get_payload(decode=True).decode('utf-8', errors='ignore'))
                    except:
                        pass
        else:
            try:
                body_parts.append(msg.get_payload(decode=True).decode('utf-8', errors='ignore'))
            except:
                body_parts.append("Unable to decode message body")
        
        return "\n".join(body_parts) if body_parts else "No text content found"
    
    @on(Button.Pressed, "#close")
    def close_modal(self) -> None:
        self.dismiss()

class RoundcubeDownloader(App):
    """Main TUI application for downloading emails from Roundcube"""
    
    CSS = """
    #modal-container {
        align: center middle;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        width: 60;
        height: 20;
    }
    
    #preview-container {
        align: center middle;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        width: 80%;
        height: 80%;
    }
    
    #modal-title {
        text-style: bold;
        margin-bottom: 1;
    }
    
    #button-container {
        margin-top: 1;
        align: center middle;
        height: 3;
    }
    
    #folder-tree {
        width: 30;
        border: solid $primary;
    }
    
    #email-table {
        border: solid $primary;
    }
    
    .progress-container {
        height: 3;
        margin: 1;
    }
    
    Input {
        margin-bottom: 1;
    }
    
    Button {
        margin: 0 1;
    }
    
    #preview-content {
        height: 70%;
        margin: 1 0;
    }
    """
    
    BINDINGS = [
        ("a", "add_account", "Add Account"),
        ("r", "refresh", "Refresh"),
        ("d", "download", "Download"),
        ("p", "preview", "Preview"),
        ("q", "quit", "Quit"),
    ]
    
    def __init__(self):
        super().__init__()
        self.accounts: List[Account] = []
        self.current_account: Optional[Account] = None
        self.current_connection: Optional[imaplib.IMAP4_SSL] = None
        self.emails: List[EmailMessage] = []
        self.selected_emails: set = set()
        self.download_formats = {
            "EML": True,
            "MBOX": False,
            "JSON": False,
            "CSV": False
        }
        
    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        
        with TabbedContent():
            with TabPane("Accounts", id="accounts-tab"):
                yield Container(
                    ListView(id="account-list"),
                    Horizontal(
                        Button("Add Account", id="add-account-btn"),
                        Button("Remove Account", id="remove-account-btn"),
                        Button("Connect", id="connect-btn"),
                    ),
                    id="accounts-container"
                )
            
            with TabPane("Browse & Download", id="browse-tab"):
                with Horizontal():
                    yield Tree("Folders", id="folder-tree")
                    
                    with Vertical():
                        yield Container(
                            Label("Search:", id="search-label"),
                            Input(placeholder="Search emails...", id="search-input"),
                            Horizontal(
                                Select(
                                    [(name, name) for name in ["All", "Subject", "From", "To", "Body"]],
                                    value="All",
                                    id="search-field"
                                ),
                                Button("Search", id="search-btn"),
                                Button("Clear", id="clear-search-btn"),
                            ),
                            id="search-container"
                        )
                        
                        yield DataTable(id="email-table")
                        
                        yield Container(
                            Label("Export Formats:", id="format-label"),
                            Horizontal(
                                Checkbox("EML", value=True, id="format-eml"),
                                Checkbox("MBOX", id="format-mbox"),
                                Checkbox("JSON", id="format-json"),
                                Checkbox("CSV", id="format-csv"),
                                id="format-checkboxes"
                            ),
                            id="format-container"
                        )
                        
                        yield Container(
                            ProgressBar(id="download-progress"),
                            Label("Ready", id="status-label"),
                            id="progress-container",
                            classes="progress-container"
                        )
                        
                        yield Horizontal(
                            Button("Select All", id="select-all-btn"),
                            Button("Deselect All", id="deselect-all-btn"),
                            Button("Preview", id="preview-btn"),
                            Button("Download Selected", id="download-btn", variant="primary"),
                            id="action-buttons"
                        )
            
            with TabPane("Settings", id="settings-tab"):
                yield Container(
                    Label("Download Directory:", id="dir-label"),
                    Input(value="./email_downloads", id="download-dir"),
                    Button("Browse", id="browse-dir-btn"),
                    Label("Concurrent Downloads:", id="concurrent-label"),
                    Input(value="5", id="concurrent-downloads"),
                    Checkbox("Preserve folder structure", value=True, id="preserve-structure"),
                    Checkbox("Skip existing files", value=True, id="skip-existing"),
                    id="settings-container"
                )
    
    async def on_mount(self) -> None:
        """Initialize the application"""
        self.load_accounts()
        self.setup_email_table()
    
    def setup_email_table(self) -> None:
        """Setup the email data table"""
        table = self.query_one("#email-table", DataTable)
        table.add_columns("✓", "Subject", "From", "Date", "Size", "Folder")
        table.cursor_type = "row"
    
    def load_accounts(self) -> None:
        """Load saved accounts from disk"""
        accounts_file = Path("accounts.pkl")
        if accounts_file.exists():
            try:
                with open(accounts_file, "rb") as f:
                    self.accounts = pickle.load(f)
                self.update_account_list()
            except Exception as e:
                self.notify(f"Error loading accounts: {str(e)}", severity="error")
    
    def save_accounts(self) -> None:
        """Save accounts to disk"""
        try:
            with open("accounts.pkl", "wb") as f:
                pickle.dump(self.accounts, f)
        except Exception as e:
            self.notify(f"Error saving accounts: {str(e)}", severity="error")
    
    def update_account_list(self) -> None:
        """Update the account list view"""
        account_list = self.query_one("#account-list", ListView)
        account_list.clear()
        
        for account in self.accounts:
            account_list.append(ListItem(Label(f"{account.name} ({account.username})")))
    
    async def action_add_account(self) -> None:
        """Show add account modal"""
        account = await self.push_screen(AddAccountModal())
        if account:
            self.accounts.append(account)
            self.save_accounts()
            self.update_account_list()
            self.notify(f"Account '{account.name}' added successfully")
    
    @on(Button.Pressed, "#add-account-btn")
    async def add_account_clicked(self) -> None:
        await self.action_add_account()
    
    @on(Button.Pressed, "#connect-btn")
    async def connect_to_account(self) -> None:
        """Connect to selected account"""
        account_list = self.query_one("#account-list", ListView)
        if account_list.index is not None and 0 <= account_list.index < len(self.accounts):
            self.current_account = self.accounts[account_list.index]
            await self.connect_imap()
    
    @work(exclusive=True)
    async def connect_imap(self) -> None:
        """Connect to IMAP server"""
        if not self.current_account:
            return
        
        self.update_status("Connecting to server...")
        
        try:
            if self.current_connection:
                self.current_connection.logout()
            
            # Connect to server
            if self.current_account.use_ssl:
                self.current_connection = imaplib.IMAP4_SSL(
                    self.current_account.server,
                    self.current_account.port
                )
            else:
                self.current_connection = imaplib.IMAP4(
                    self.current_account.server,
                    self.current_account.port
                )
            
            # Login
            self.current_connection.login(
                self.current_account.username,
                self.current_account.password
            )
            
            self.notify(f"Connected to {self.current_account.name}")
            self.update_status("Connected")
            
            # Load folders
            await self.load_folders()
            
        except Exception as e:
            self.notify(f"Connection error: {str(e)}", severity="error")
            self.update_status("Connection failed")
    
    async def load_folders(self) -> None:
        """Load folder structure from IMAP"""
        if not self.current_connection:
            return
        
        tree = self.query_one("#folder-tree", Tree)
        tree.clear()
        
        try:
            # Get folder list
            status, folders = self.current_connection.list()
            
            if status == "OK":
                root = tree.root
                folder_dict = {}
                
                for folder_line in folders:
                    if folder_line:
                        # Parse folder info
                        parts = folder_line.decode('utf-8').split('"')
                        if len(parts) >= 3:
                            folder_name = parts[-2]
                            
                            # Handle hierarchical folders
                            if "/" in folder_name:
                                parent_path = "/".join(folder_name.split("/")[:-1])
                                folder_short_name = folder_name.split("/")[-1]
                                
                                if parent_path in folder_dict:
                                    node = folder_dict[parent_path].add(folder_short_name)
                                else:
                                    node = root.add(folder_name)
                            else:
                                node = root.add(folder_name)
                            
                            folder_dict[folder_name] = node
                
                tree.root.expand()
                
        except Exception as e:
            self.notify(f"Error loading folders: {str(e)}", severity="error")
    
    @on(Tree.NodeSelected)
    async def folder_selected(self, event: Tree.NodeSelected) -> None:
        """Handle folder selection"""
        if not self.current_connection:
            return
        
        folder_name = str(event.node.label)
        await self.load_emails(folder_name)
    
    @work(exclusive=True)
    async def load_emails(self, folder: str) -> None:
        """Load emails from selected folder"""
        self.update_status(f"Loading emails from {folder}...")
        
        try:
            # Select folder
            status, data = self.current_connection.select(f'"{folder}"')
            
            if status != "OK":
                self.notify(f"Cannot select folder: {folder}", severity="error")
                return
            
            # Search for all emails
            status, data = self.current_connection.search(None, "ALL")
            
            if status == "OK":
                email_ids = data[0].split()
                self.emails.clear()
                
                # Load email headers
                total = len(email_ids)
                for idx, email_id in enumerate(email_ids):
                    if idx % 10 == 0:
                        self.update_status(f"Loading emails... {idx}/{total}")
                    
                    # Fetch email headers
                    status, data = self.current_connection.fetch(
                        email_id,
                        "(UID BODY[HEADER.FIELDS (SUBJECT FROM DATE)] RFC822.SIZE)"
                    )
                    
                    if status == "OK":
                        for response_part in data:
                            if isinstance(response_part, tuple):
                                msg = email.message_from_bytes(response_part[1])
                                
                                # Extract UID
                                uid_data = response_part[0].decode('utf-8')
                                uid = uid_data.split("UID ")[1].split(" ")[0]
                                
                                # Extract size
                                size_match = uid_data.split("RFC822.SIZE ")[1].split(")")[0]
                                size = int(size_match) if size_match.isdigit() else 0
                                
                                email_msg = EmailMessage(
                                    uid=uid,
                                    subject=msg.get("Subject", "No Subject"),
                                    sender=msg.get("From", "Unknown"),
                                    date=msg.get("Date", "Unknown"),
                                    size=size,
                                    folder=folder
                                )
                                self.emails.append(email_msg)
                
                self.update_email_table()
                self.update_status(f"Loaded {len(self.emails)} emails from {folder}")
                
        except Exception as e:
            self.notify(f"Error loading emails: {str(e)}", severity="error")
            self.update_status("Error loading emails")
    
    def update_email_table(self) -> None:
        """Update the email data table"""
        table = self.query_one("#email-table", DataTable)
        table.clear()
        
        for email_msg in self.emails:
            selected = "✓" if email_msg.uid in self.selected_emails else ""
            size_kb = email_msg.size // 1024
            table.add_row(
                selected,
                email_msg.subject[:50] + ("..." if len(email_msg.subject) > 50 else ""),
                email_msg.sender[:30] + ("..." if len(email_msg.sender) > 30 else ""),
                email_msg.date[:20],
                f"{size_kb} KB",
                email_msg.folder
            )
    
    @on(DataTable.RowSelected)
    def email_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle email row selection"""
        if 0 <= event.row_index < len(self.emails):
            email_msg = self.emails[event.row_index]
            
            if email_msg.uid in self.selected_emails:
                self.selected_emails.remove(email_msg.uid)
            else:
                self.selected_emails.add(email_msg.uid)
            
            self.update_email_table()
    
    @on(Button.Pressed, "#select-all-btn")
    def select_all_emails(self) -> None:
        """Select all emails"""
        self.selected_emails = {email.uid for email in self.emails}
        self.update_email_table()
    
    @on(Button.Pressed, "#deselect-all-btn")
    def deselect_all_emails(self) -> None:
        """Deselect all emails"""
        self.selected_emails.clear()
        self.update_email_table()
    
    @on(Button.Pressed, "#preview-btn")
    async def preview_email(self) -> None:
        """Preview selected email"""
        table = self.query_one("#email-table", DataTable)
        
        if table.cursor_row is not None and 0 <= table.cursor_row < len(self.emails):
            email_msg = self.emails[table.cursor_row]
            
            # Fetch full email
            if self.current_connection:
                try:
                    status, data = self.current_connection.select(f'"{email_msg.folder}"')
                    if status == "OK":
                        status, data = self.current_connection.uid("fetch", email_msg.uid, "(RFC822)")
                        if status == "OK":
                            email_msg.raw_email = data[0][1]
                            await self.push_screen(EmailPreviewModal(email_msg))
                except Exception as e:
                    self.notify(f"Error fetching email: {str(e)}", severity="error")
    
    @on(Button.Pressed, "#download-btn")
    async def download_selected(self) -> None:
        """Download selected emails"""
        if not self.selected_emails:
            self.notify("No emails selected", severity="warning")
            return
        
        # Get export formats
        formats = []
        if self.query_one("#format-eml", Checkbox).value:
            formats.append("EML")
        if self.query_one("#format-mbox", Checkbox).value:
            formats.append("MBOX")
        if self.query_one("#format-json", Checkbox).value:
            formats.append("JSON")
        if self.query_one("#format-csv", Checkbox).value:
            formats.append("CSV")
        
        if not formats:
            self.notify("Please select at least one export format", severity="warning")
            return
        
        await self.download_emails(formats)
    
    @work(exclusive=True)
    async def download_emails(self, formats: List[str]) -> None:
        """Download emails in specified formats"""
        download_dir = Path(self.query_one("#download-dir", Input).value)
        download_dir.mkdir(parents=True, exist_ok=True)
        
        selected_emails = [e for e in self.emails if e.uid in self.selected_emails]
        total = len(selected_emails)
        
        progress_bar = self.query_one("#download-progress", ProgressBar)
        progress_bar.update(total=total, progress=0)
        
        # Group by folder for MBOX
        folder_emails = {}
        for email_msg in selected_emails:
            if email_msg.folder not in folder_emails:
                folder_emails[email_msg.folder] = []
            folder_emails[email_msg.folder].append(email_msg)
        
        # Prepare storage
        json_data = []
        csv_data = []
        
        for idx, email_msg in enumerate(selected_emails):
            self.update_status(f"Downloading {idx + 1}/{total}: {email_msg.subject[:30]}...")
            
            try:
                # Select folder and fetch email
                status, _ = self.current_connection.select(f'"{email_msg.folder}"')
                if status == "OK":
                    status, data = self.current_connection.uid("fetch", email_msg.uid, "(RFC822)")
                    
                    if status == "OK":
                        raw_email = data[0][1]
                        msg = email.message_from_bytes(raw_email)
                        
                        # Create folder structure if needed
                        if self.query_one("#preserve-structure", Checkbox).value:
                            folder_path = download_dir / email_msg.folder.replace("/", os.sep)
                            folder_path.mkdir(parents=True, exist_ok=True)
                        else:
                            folder_path = download_dir
                        
                        # Save as EML
                        if "EML" in formats:
                            safe_subject = "".join(c for c in email_msg.subject if c.isalnum() or c in " -_")[:50]
                            filename = f"{email_msg.uid}_{safe_subject}.eml"
                            filepath = folder_path / filename
                            
                            if not filepath.exists() or not self.query_one("#skip-existing", Checkbox).value:
                                with open(filepath, "wb") as f:
                                    f.write(raw_email)
                        
                        # Prepare for JSON
                        if "JSON" in formats:
                            json_data.append({
                                "uid": email_msg.uid,
                                "subject": email_msg.subject,
                                "from": email_msg.sender,
                                "date": email_msg.date,
                                "folder": email_msg.folder,
                                "size": email_msg.size,
                                "body": self.extract_body_for_export(msg)
                            })
                        
                        # Prepare for CSV
                        if "CSV" in formats:
                            csv_data.append({
                                "UID": email_msg.uid,
                                "Subject": email_msg.subject,
                                "From": email_msg.sender,
                                "Date": email_msg.date,
                                "Folder": email_msg.folder,
                                "Size": email_msg.size
                            })
                        
            except Exception as e:
                self.notify(f"Error downloading email {email_msg.uid}: {str(e)}", severity="error")
            
            progress_bar.update(progress=idx + 1)
        
        # Save MBOX files
        if "MBOX" in formats:
            for folder, emails in folder_emails.items():
                mbox_path = download_dir / f"{folder.replace('/', '_')}.mbox"
                mbox = mailbox.mbox(str(mbox_path))
                
                for email_msg in emails:
                    try:
                        status, _ = self.current_connection.select(f'"{email_msg.folder}"')
                        if status == "OK":
                            status, data = self.current_connection.uid("fetch", email_msg.uid, "(RFC822)")
                            if status == "OK":
                                msg = email.message_from_bytes(data[0][1])
                                mbox.add(msg)
                    except Exception as e:
                        self.notify(f"Error adding to MBOX: {str(e)}", severity="error")
                
                mbox.close()
        
        # Save JSON
        if "JSON" in formats and json_data:
            json_path = download_dir / "emails.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
        
        # Save CSV
        if "CSV" in formats and csv_data:
            csv_path = download_dir / "emails.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=csv_data[0].keys())
                writer.writeheader()
                writer.writerows(csv_data)
        
        self.update_status(f"Downloaded {total} emails successfully")
        self.notify(f"Downloaded {total} emails to {download_dir}")
    
    def extract_body_for_export(self, msg) -> str:
        """Extract email body for export"""
        body_parts = []
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain" or content_type == "text/html":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body_parts.append(payload.decode('utf-8', errors='ignore'))
                    except:
                        pass
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    body_parts.append(payload.decode('utf-8', errors='ignore'))
            except:
                pass
        
        return "\n---\n".join(body_parts) if body_parts else ""
    
    @on(Button.Pressed, "#search-btn")
    async def search_emails(self) -> None:
        """Search emails"""
        search_term = self.query_one("#search-input", Input).value
        search_field = self.query_one("#search-field", Select).value
        
        if not search_term:
            self.update_email_table()
            return
        
        # Filter emails based on search
        filtered_emails = []
        search_lower = search_term.lower()
        
        for email_msg in self.emails:
            match = False
            
            if search_field == "All":
                match = (search_lower in email_msg.subject.lower() or
                        search_lower in email_msg.sender.lower())
            elif search_field == "Subject":
                match = search_lower in email_msg.subject.lower()
            elif search_field == "From":
                match = search_lower in email_msg.sender.lower()
            
            if match:
                filtered_emails.append(email_msg)
        
        # Update table with filtered results
        table = self.query_one("#email-table", DataTable)
        table.clear()
        
        for email_msg in filtered_emails:
            selected = "✓" if email_msg.uid in self.selected_emails else ""
            size_kb = email_msg.size // 1024
            table.add_row(
                selected,
                email_msg.subject[:50] + ("..." if len(email_msg.subject) > 50 else ""),
                email_msg.sender[:30] + ("..." if len(email_msg.sender) > 30 else ""),
                email_msg.date[:20],
                f"{size_kb} KB",
                email_msg.folder
            )
        
        self.update_status(f"Found {len(filtered_emails)} matching emails")
    
    @on(Button.Pressed, "#clear-search-btn")
    def clear_search(self) -> None:
        """Clear search and show all emails"""
        self.query_one("#search-input", Input).value = ""
        self.update_email_table()
    
    def update_status(self, message: str) -> None:
        """Update status label"""
        self.query_one("#status-label", Label).update(message)
    
    async def action_refresh(self) -> None:
        """Refresh current folder"""
        tree = self.query_one("#folder-tree", Tree)
        if tree.cursor_node and tree.cursor_node.label:
            await self.load_emails(str(tree.cursor_node.label))
    
    async def action_download(self) -> None:
        """Download selected emails"""
        await self.download_selected()
    
    async def action_preview(self) -> None:
        """Preview selected email"""
        await self.preview_email()

if __name__ == "__main__":
    app = RoundcubeDownloader()
    app.run()
