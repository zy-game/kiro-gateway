import sqlite3

conn = sqlite3.connect('data/accounts.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables in database:")
for table in tables:
    print(f"  - {table[0]}")

print("\n" + "="*60 + "\n")

# Check if models table exists
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='models'")
result = cursor.fetchone()
if result:
    print("Models table schema:")
    print(result[0])
else:
    print("Models table does not exist")

conn.close()
