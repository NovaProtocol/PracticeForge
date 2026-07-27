"""SQLAlchemy engine and session factory."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.sqlalchemy_models import Base

DSN = (
    f"mysql+pymysql://{os.environ.get('MYSQL_USER', 'root')}:{os.environ['MYSQL_PASS']}"
    f"@{os.environ['MYSQL_HOST']}:{os.environ.get('MYSQL_PORT', '3306')}"
    f"/{os.environ['MYSQL_DATABASE']}"
)

engine = create_engine(DSN, pool_pre_ping=True, pool_recycle=300)
Session = sessionmaker(bind=engine)
