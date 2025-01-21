import os
import dotenv

dotenv.load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "No key found")
print(DATABASE_URL)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
print(FRONTEND_URL)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "No key found")