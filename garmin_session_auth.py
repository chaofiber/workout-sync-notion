"""
Garmin Session-Based Authentication
This module provides session-based authentication for Garmin Connect
to avoid triggering security alerts when logging in from different locations.
"""

import os
import pickle  # nosec B403 - We only load our own trusted session files
from datetime import datetime, timedelta
from pathlib import Path

from garminconnect import Garmin, GarminConnectAuthenticationError


class GarminSessionAuth:
    """
    Handle Garmin authentication with session persistence.
    Sessions are saved and reused to avoid frequent re-authentication.
    """

    def __init__(self, email=None, password=None, session_dir=".garmin_session"):
        """
        Initialize Garmin session authentication.

        Args:
            email: Garmin email (can be None if using existing session)
            password: Garmin password (can be None if using existing session)
            session_dir: Directory to store session files
        """
        self.email = email or os.getenv("GARMIN_EMAIL")
        self.password = password or os.getenv("GARMIN_PASSWORD")
        self.session_dir = Path(session_dir)
        self.session_file = self.session_dir / "session.pkl"
        self.garmin = None

        # Create session directory if it doesn't exist
        self.session_dir.mkdir(exist_ok=True)

    def login(self, force_refresh=False):
        """
        Login to Garmin Connect using saved session or credentials.

        Args:
            force_refresh: Force a fresh login even if session exists

        Returns:
            Garmin client object
        """
        # Try to use existing session unless forced to refresh
        if not force_refresh and self.session_file.exists():
            try:
                return self._login_with_session()
            except Exception as e:
                print(f"Session login failed: {e}")
                print("Attempting fresh login...")

        # Perform fresh login
        return self._fresh_login()

    def _login_with_session(self):
        """Load and use existing session."""
        print("Loading existing session...")

        with open(self.session_file, "rb") as f:
            session_data = pickle.load(f)  # nosec B301 - Loading our own session file

        # Check if session is not too old (refresh every 360 days)
        session_age = datetime.now() - session_data["timestamp"]
        if session_age > timedelta(days=360):
            raise Exception(f"Session too old ({session_age.days} days)")

        # Initialize Garmin and restore session
        self.garmin = Garmin()
        self.garmin.garth.loads(session_data["session"])

        # Validate session is still active
        try:
            # Test API call to verify session
            self.garmin.get_full_name()
            print(f"Session valid (age: {session_age.days} days)")
            return self.garmin
        except GarminConnectAuthenticationError:
            raise Exception("Session expired or invalid")

    def _fresh_login(self):
        """Perform a fresh login and save session."""
        if not self.email or not self.password:
            raise ValueError("Email and password required for fresh login")

        print("Performing fresh login...")
        self.garmin = Garmin(self.email, self.password)
        self.garmin.login()

        # Save session for future use
        self._save_session()

        return self.garmin

    def _save_session(self):
        """Save current session to file."""
        try:
            # garminconnect uses garth for authentication
            # Save the garth session token
            session_data = {
                "session": self.garmin.garth.dumps(),
                "timestamp": datetime.now(),
                "email": self.email,  # Store email for reference
            }

            with open(self.session_file, "wb") as f:
                pickle.dump(session_data, f)  # nosec B301 - Saving our own session

            # Set restrictive permissions (Unix-like systems)
            os.chmod(self.session_file, 0o600)

            print(f"Session saved to {self.session_file}")
        except Exception as e:
            print(f"Warning: Could not save session: {e}")

    def export_session_for_github(self):
        """
        Export session data as base64 string for GitHub secrets.
        This allows the session to be stored as a GitHub secret.
        """
        import base64

        if not self.session_file.exists():
            raise Exception("No session file exists. Login first.")

        with open(self.session_file, "rb") as f:
            session_bytes = f.read()

        # Convert to base64 for easy storage in GitHub secrets
        session_b64 = base64.b64encode(session_bytes).decode("utf-8")

        print("\n" + "=" * 60)
        print("SESSION DATA FOR GITHUB SECRET")
        print("=" * 60)
        print("\nAdd this as a GitHub secret named 'GARMIN_SESSION':")
        print("\n" + session_b64)
        print("\n" + "=" * 60)

        return session_b64

    def import_session_from_github(self, session_b64):
        """
        Import session data from base64 string (from GitHub secrets).

        Args:
            session_b64: Base64 encoded session data
        """
        import base64

        # Decode base64 and save to file
        session_bytes = base64.b64decode(session_b64)

        with open(self.session_file, "wb") as f:
            f.write(session_bytes)

        # Set restrictive permissions
        os.chmod(self.session_file, 0o600)

        print(f"Session imported to {self.session_file}")


def get_garmin_client():
    """
    Convenience function to get an authenticated Garmin client.
    Uses session if available, otherwise falls back to credentials.
    """
    # Check if we have a session from GitHub Actions
    github_session = os.getenv("GARMIN_SESSION")

    auth = GarminSessionAuth()

    if github_session:
        print("Using session from GitHub secret...")
        auth.import_session_from_github(github_session)

    return auth.login()


if __name__ == "__main__":
    import sys

    # Command-line interface for managing sessions
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "login":
            # Create new session
            auth = GarminSessionAuth()
            auth.login(force_refresh=True)
            print("\nSession created successfully!")

        elif command == "export":
            # Export session for GitHub
            auth = GarminSessionAuth()
            auth.export_session_for_github()

        elif command == "test":
            # Test current session
            auth = GarminSessionAuth()
            garmin = auth.login()
            profile = garmin.get_user_profile()
            name = profile.get("displayName", profile.get("userName", "Unknown"))
            print(f"Authenticated as: {name}")

        else:
            print("Unknown command. Use: login, export, or test")
    else:
        print("Garmin Session Authentication Manager")
        print("\nUsage:")
        print("  python garmin_session_auth.py login   - Create new session")
        print("  python garmin_session_auth.py export  - Export session for GitHub")
        print("  python garmin_session_auth.py test    - Test current session")
