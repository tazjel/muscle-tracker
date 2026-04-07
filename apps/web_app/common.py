from py4web import DAL, Session, Auth, Translator, action, request, response, URL
from py4web.utils.cors import CORS
import os

# --- DATABASE SETUP ---
DB_FOLDER = os.path.join(os.path.dirname(__file__), 'databases')
if not os.path.exists(DB_FOLDER):
    os.makedirs(DB_FOLDER)

# Use the existing database.db from the apps folder
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database.db')
db = DAL('sqlite://' + os.path.abspath(DB_PATH), folder=DB_FOLDER, fake_migrate_all=True)

# --- FIXTURES ---
session = Session(secret='secret_key')
cors = CORS()

# No auth for now as requested
auth = Auth(session, db)
auth.enable()

# --- EXPORTS ---
__all__ = ['db', 'session', 'auth', 'cors']
