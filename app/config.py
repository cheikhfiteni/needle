import os

DATABASE_URL = os.getenv("DATABASE_URL", "No key found")
print(DATABASE_URL)
