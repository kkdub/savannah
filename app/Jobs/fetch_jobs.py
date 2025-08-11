from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import os
import requests
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.crud import get_last_fetch, set