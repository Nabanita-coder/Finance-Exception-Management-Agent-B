import os
from urllib.parse import quote_plus
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# .env থেকে ক্রেডেনশিয়াল লোড
load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = quote_plus(os.getenv("DB_PASSWORD", ""))
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ডাটাবেজ ইঞ্জিন তৈরি
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# ডাটাবেজ কানেকশন টেস্ট
try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("Database connected successfully!")
except Exception as e:
    print(f"Database connection failed: {e}")


def get_session():
    return SessionLocal()
