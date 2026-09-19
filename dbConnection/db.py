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


def call_sp(sp_name: str, params: list = None):
    """
    Executes a MySQL stored procedure using the engine connection
    and returns the result rows as a list of dictionaries.
    """
    if params is None:
        params = []
    
    # Construct parameter placeholders: CALL sp_name(:p0, :p1, ...) or CALL sp_name()
    if params:
        param_placeholders = ", ".join([f":p{i}" for i in range(len(params))])
        sql = text(f"CALL {sp_name}({param_placeholders})")
        param_dict = {f"p{i}": val for i, val in enumerate(params)}
    else:
        sql = text(f"CALL {sp_name}()")
        param_dict = {}

    with engine.begin() as conn:
        result = conn.execute(sql, param_dict)
        if result.returns_rows:
            columns = result.keys()
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
            return rows
        return []

