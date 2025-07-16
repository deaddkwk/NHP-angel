import firebase_admin
from firebase_admin import credentials, db
import os

# Render에서는 환경변수를 통해 인증 키와 DB URL을 관리할 수 있음
SERVICE_ACCOUNT_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json")
DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL", "https://your-project-id.firebaseio.com")

cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
firebase_admin.initialize_app(cred, {
    "databaseURL": DATABASE_URL
})

def save_player(call_sign, data):
    ref = db.reference(f"players/{call_sign}")
    ref.set(data)

def get_player(call_sign):
    ref = db.reference(f"players/{call_sign}")
    return ref.get()

def delete_player(call_sign):
    ref = db.reference(f"players/{call_sign}")
    ref.delete()

def get_all_players():
    ref = db.reference("players")
    return ref.get() or {}

def player_exists(call_sign):
    return get_player(call_sign) is not None
