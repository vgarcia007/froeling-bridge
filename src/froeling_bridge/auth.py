"""Local accounts and revocable credentials; no controller or history access."""
import argparse
from contextlib import contextmanager
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
from threading import BoundedSemaphore
import time

from .errors import ValidationError, ReadOnlyViolation


COOKIE = "__Host-froeling_session"
READ_JOBS = frozenset(("status", "firmware", "discover_menu", "measurement",
                      "read_menu_value", "read_parameter", "time_ranges", "refresh_component"))
WRITE_JOBS = frozenset(("write_parameter", "write_time_range"))
HASH_SLOTS = BoundedSemaphore(2)


class AuthUnavailable(Exception):
    pass


class Throttled(Exception):
    def __init__(self, retry_after=60):
        self.retry_after = max(1, int(retry_after))


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def username(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value):
        raise ValidationError("username requires 1..64 letters, numbers, dots, underscores or hyphens")
    return value.lower()


class AuthStore:
    def __init__(self, path):
        from argon2 import PasswordHasher, Type
        self.path = Path(path)
        self.hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1, type=Type.ID)
        self.dummy_hash = self.hasher.hash(secrets.token_urlsafe(32))
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise ValidationError("authentication database symlink refused")
        # Create privately before sqlite opens it, including for console provisioning.
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        self.path.chmod(0o600)
        with self.db() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValidationError("unsupported authentication database")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
              CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('read','write')),
                enabled INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS sessions (
                hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                csrf TEXT NOT NULL, created REAL NOT NULL, seen REAL NOT NULL, expires REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), label TEXT NOT NULL,
                hash TEXT UNIQUE NOT NULL, scope TEXT NOT NULL CHECK(scope IN ('read','write')),
                created REAL NOT NULL, expires REAL, revoked INTEGER NOT NULL DEFAULT 0);
              CREATE TABLE IF NOT EXISTS limits (key TEXT PRIMARY KEY, started REAL NOT NULL, count INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, time REAL NOT NULL, event TEXT NOT NULL,
                user_id INTEGER, credential_id TEXT, detail TEXT);
              PRAGMA user_version=1;
            """)

    @contextmanager
    def db(self):
        db = None
        try:
            db = sqlite3.connect(self.path, timeout=.5)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        except sqlite3.Error:
            raise AuthUnavailable("authentication storage unavailable") from None
        finally:
            if db is not None:
                db.close()

    def event(self, event, actor=None, detail=None):
        with self.db() as db:
            db.execute("INSERT INTO events(time,event,user_id,credential_id,detail) VALUES(?,?,?,?,?)",
                       (time.time(), event, (actor or {}).get("user_id"), (actor or {}).get("id"), detail))
            db.execute("DELETE FROM events WHERE time<?", (time.time()-30*86400,))

    @staticmethod
    def check_password(password):
        if not isinstance(password, str) or not 15 <= len(password) <= 128:
            raise ValidationError("password requires 15..128 characters")

    def add_user(self, name, password, role):
        name = username(name)
        self.check_password(password)
        if role not in ("read", "write"):
            raise ValidationError("role must be read or write")
        hashed = self.hasher.hash(password)
        with self.db() as db:
            if db.execute("SELECT id FROM users WHERE username=?", (name,)).fetchone():
                raise ValidationError("user already exists")
            db.execute("INSERT INTO users(username,password_hash,role,created) VALUES(?,?,?,?)",
                       (name, hashed, role, time.time()))
        self.event("user_created", detail=name)

    def change_user(self, name, *, password=None, role=None, enabled=None):
        name = username(name)
        if role is not None and role not in ("read", "write"):
            raise ValidationError("role must be read or write")
        hashed = None
        if password is not None:
            self.check_password(password)
            hashed = self.hasher.hash(password)
        with self.db() as db:
            user = db.execute("SELECT id FROM users WHERE username=?", (name,)).fetchone()
            if not user:
                raise ValidationError("unknown user")
            for field, value in (("password_hash", hashed), ("role", role), ("enabled", enabled)):
                if value is not None:
                    db.execute("UPDATE users SET " + field + "=? WHERE id=?", (value, user["id"]))
            if hashed is not None or enabled is False:
                db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            if enabled is False:
                db.execute("UPDATE api_keys SET revoked=1 WHERE user_id=?", (user["id"],))
        self.event("user_changed", detail=name)

    def users(self):
        with self.db() as db:
            return [dict(row) for row in db.execute("SELECT username,role,enabled,created FROM users ORDER BY username")]

    def create_key(self, name, label, scope="read", expires=None):
        if scope not in ("read", "write") or not isinstance(label, str) or not 1 <= len(label) <= 80:
            raise ValidationError("key requires a label and read/write scope")
        if expires is not None and expires <= time.time():
            raise ValidationError("key expiry must be in the future")
        identifier = secrets.token_hex(8)
        token = "fbk_" + identifier + "." + secrets.token_urlsafe(32)
        with self.db() as db:
            user = db.execute("SELECT id,role,enabled FROM users WHERE username=?", (username(name),)).fetchone()
            if not user or not user["enabled"] or (scope == "write" and user["role"] != "write"):
                raise ValidationError("user is missing, disabled or lacks requested key rights")
            db.execute("INSERT INTO api_keys(id,user_id,label,hash,scope,created,expires) VALUES(?,?,?,?,?,?,?)",
                       (identifier, user["id"], label, digest(token), scope, time.time(), expires))
        self.event("key_created", detail=identifier)
        return token

    def keys(self, name):
        with self.db() as db:
            return [dict(row) for row in db.execute(
                "SELECT k.id,k.label,k.scope,k.created,k.expires,k.revoked FROM api_keys k "
                "JOIN users u ON u.id=k.user_id WHERE u.username=? ORDER BY k.created", (username(name),))]

    def revoke_key(self, identifier):
        with self.db() as db:
            if not db.execute("SELECT id FROM api_keys WHERE id=?", (identifier,)).fetchone():
                raise ValidationError("unknown key identifier")
            db.execute("UPDATE api_keys SET revoked=1 WHERE id=?", (identifier,))
        self.event("key_revoked", detail=identifier)

    def limit(self, key, maximum, window):
        now = time.time()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM limits WHERE started<?", (now-900,))
            row = db.execute("SELECT started,count FROM limits WHERE key=?", (key,)).fetchone()
            if row and row["started"] > now-window:
                if row["count"] >= maximum:
                    raise Throttled(window - (now-row['started']) + 1)
                db.execute("UPDATE limits SET count=count+1 WHERE key=?", (key,))
            else:
                db.execute("INSERT OR REPLACE INTO limits VALUES(?,?,1)", (key, now))

    def login(self, name, password, ip):
        # Charge attempts before expensive hashing, even for malformed/unknown users.
        self.limit("login-ip:" + digest(ip), 20, 900)
        try:
            normalized = username(name)
        except ValidationError:
            normalized = ""
        limit_name = normalized or str(name)[:128].casefold()
        self.limit("login-user-ip:" + digest(limit_name + "\0" + ip), 5, 900)
        if not isinstance(password, str) or not 1 <= len(password) <= 128:
            self.event("login_failed")
            return None
        if not HASH_SLOTS.acquire(blocking=False):
            raise Throttled()
        try:
            from argon2.exceptions import VerificationError, InvalidHashError
            with self.db() as db:
                row = db.execute("SELECT * FROM users WHERE username=?", (normalized,)).fetchone()
            try:
                correct = self.hasher.verify(row["password_hash"] if row else self.dummy_hash, password)
            except (VerificationError, InvalidHashError):
                correct = False
            if not correct or not row or not row["enabled"]:
                self.event("login_failed")
                return None
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            now = time.time()
            with self.db() as db:
                # Console password reset/disable during hashing must invalidate the login.
                current = db.execute("SELECT password_hash,enabled FROM users WHERE id=?", (row["id"],)).fetchone()
                if not current["enabled"] or current["password_hash"] != row["password_hash"]:
                    return None
                db.execute("DELETE FROM sessions WHERE expires<? OR seen<?", (now, now-1800))
                db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?)",
                           (digest(token), row["id"], csrf, now, now, now+43200))
                db.execute("DELETE FROM limits WHERE key=?", (
                    "login-user-ip:" + digest(limit_name + "\0" + ip),))
            self.event("login_succeeded", {"user_id": row["id"], "id": digest(token)[:16]})
            return token
        finally:
            HASH_SLOTS.release()

    def authenticate(self, token, kind, *, touch=True):
        if not isinstance(token, str) or not 20 <= len(token) <= 160:
            return None
        hashed, now = digest(token), time.time()
        with self.db() as db:
            if kind == "key":
                row = db.execute("SELECT u.id user_id,u.username,u.role,u.enabled,k.id,k.scope,k.expires,k.revoked "
                    "FROM api_keys k JOIN users u ON u.id=k.user_id WHERE k.hash=?", (hashed,)).fetchone()
                if not row or not row["enabled"] or row["revoked"] or (row["expires"] is not None and row["expires"] <= now):
                    return None
                role = "write" if row["role"] == row["scope"] == "write" else "read"
                return dict(user_id=row["user_id"], username=row["username"], role=role,
                            kind=kind, id=row["id"], credential_hash=hashed)
            row = db.execute("SELECT u.id user_id,u.username,u.role,u.enabled,s.csrf,s.expires,s.seen "
                "FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.hash=?", (hashed,)).fetchone()
            if not row or not row["enabled"] or row["expires"] <= now or row["seen"] <= now-1800:
                return None
            if touch and row["seen"] < now-30:
                db.execute("UPDATE sessions SET seen=? WHERE hash=?", (now, hashed))
            return dict(user_id=row["user_id"], username=row["username"], role=row["role"],
                        kind="session", csrf=row["csrf"], id=hashed[:16], credential_hash=hashed)

    def assert_writer(self, actor):
        """Recheck revocation and current role inside the controller queue."""
        if not actor:
            raise ReadOnlyViolation("authenticated writer required")
        now = time.time()
        with self.db() as db:
            user = db.execute("SELECT role,enabled FROM users WHERE id=?", (actor["user_id"],)).fetchone()
            if not user or not user["enabled"] or user["role"] != "write":
                raise ReadOnlyViolation("write permission revoked")
            if actor["kind"] == "key":
                valid = db.execute("SELECT 1 FROM api_keys WHERE hash=? AND user_id=? AND scope='write' "
                    "AND revoked=0 AND (expires IS NULL OR expires>?)",
                    (actor["credential_hash"], actor["user_id"], now)).fetchone()
            else:
                valid = db.execute("SELECT 1 FROM sessions WHERE hash=? AND user_id=? AND expires>? AND seen>?",
                    (actor["credential_hash"], actor["user_id"], now, now-1800)).fetchone()
            if not valid:
                raise ReadOnlyViolation("credential expired or revoked")

    def logout(self, actor):
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE hash=?", (actor["credential_hash"],))
        self.event("logout", actor)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Console-only users and API credentials")
    parser.add_argument("--state-dir", default="/var/lib/froeling-bridge")
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("add", "password", "role", "enable", "disable", "keys", "key-create"):
        cmd = commands.add_parser(action)
        cmd.add_argument("username")
        if action in ("add", "role"):
            cmd.add_argument("--role", required=True, choices=("read", "write"))
        if action in ("add", "password"):
            cmd.add_argument("--generate-password", action="store_true")
        if action == "key-create":
            cmd.add_argument("--label", required=True)
            cmd.add_argument("--scope", choices=("read", "write"), default="read")
            cmd.add_argument("--expires-days", type=int)
    commands.add_parser("list")
    revoke = commands.add_parser("key-revoke"); revoke.add_argument("identifier")
    args = parser.parse_args(argv)
    state = Path(args.state_dir)
    if os.geteuid() == 0 and state.exists() and state.stat().st_uid != 0:
        # Avoid root-owned SQLite WAL files when console and web run concurrently.
        os.setgroups([]); os.setgid(state.stat().st_gid); os.setuid(state.stat().st_uid)
    store = AuthStore(state / "auth.sqlite3")
    try:
        if args.action in ("add", "password"):
            password = secrets.token_urlsafe(24) if args.generate_password else getpass.getpass("Passwort: ")
            if not args.generate_password and password != getpass.getpass("Passwort wiederholen: "):
                raise ValidationError("passwords differ")
            if args.action == "add": store.add_user(args.username, password, args.role)
            else: store.change_user(args.username, password=password)
            if args.generate_password: print(password)
        elif args.action == "list": print(json.dumps(store.users(), indent=2))
        elif args.action == "role": store.change_user(args.username, role=args.role)
        elif args.action in ("enable", "disable"): store.change_user(args.username, enabled=args.action == "enable")
        elif args.action == "keys": print(json.dumps(store.keys(args.username), indent=2))
        elif args.action == "key-revoke": store.revoke_key(args.identifier)
        elif args.action == "key-create":
            expiry = time.time()+args.expires_days*86400 if args.expires_days is not None else None
            print(store.create_key(args.username, args.label, args.scope, expiry))
    except (ValidationError, AuthUnavailable) as exc:
        parser.exit(2, str(exc) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
