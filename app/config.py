from dotenv import load_dotenv
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

print("BASE_DIR =", BASE_DIR)

env_path = BASE_DIR / ".env"

print("ENV PATH =", env_path)

result = load_dotenv(env_path)

print("LOAD RESULT =", result)

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

print("EMAIL_SENDER =", EMAIL_SENDER)
print("EMAIL_PASSWORD =", EMAIL_PASSWORD)