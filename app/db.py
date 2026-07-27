import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
load_dotenv()

Base = declarative_base()

DB_URL = os.environ.get("DATABASE_URL", "sqlite:///wallet.db")

if not DB_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_engine(DB_URL, future=True)

SessionLocal = sessionmaker(bind=engine, future=True)

from . models import *
