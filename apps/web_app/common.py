from py4web import DAL, Session, Translator, action, request, response, URL
from py4web.utils.auth import Auth
from py4web.utils.cors import CORS
import os

# --- DATABASE SETUP ---
DB_FOLDER = os.path.join(os.path.dirname(__file__), 'databases')
if not os.path.exists(DB_FOLDER):
    os.makedirs(DB_FOLDER)

# Use the existing database.db from the project root
# dirname(__file__) = apps/web_app -> .. -> apps -> .. -> root
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'database.db'))

# On Windows, pyDAL needs sqlite:///C:/... (3 slashes) or it might misinterpret the drive colon
uri = 'sqlite://' + DB_PATH.replace('\\', '/')
db = DAL(uri, folder=DB_FOLDER, fake_migrate_all=True)

# --- FIXTURES ---
session = Session(secret='secret_key')
cors = CORS()

# No auth for now as requested
auth = Auth(session, db)
auth.enable()

# --- EXPORTS ---
__all__ = ['db', 'session', 'auth', 'cors']
