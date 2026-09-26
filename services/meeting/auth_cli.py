"""One-time local account setup for the meeting service."""

import argparse
from getpass import getpass

from .auth import AuthService
from .storage import Storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Secure MOM local account administration")
    subcommands = parser.add_subparsers(dest="command", required=True)
    bootstrap = subcommands.add_parser("bootstrap-admin", help="create the first local administrator")
    bootstrap.add_argument("--username", required=True)
    args = parser.parse_args()

    store = Storage()
    if store.user_count():
        parser.error("Accounts already exist; bootstrap is one-time")
    password = getpass("New administrator password (12+ characters): ")
    confirm = getpass("Confirm password: ")
    if password != confirm:
        parser.error("Passwords do not match")
    try:
        AuthService(store).create_user(store.installation_organization(), args.username,
                                      password, "administrator", bootstrap=True)
    except ValueError as exc:
        parser.error(str(exc))
    print("Local administrator created. Sign in through the app's local service.")


if __name__ == "__main__":
    main()
