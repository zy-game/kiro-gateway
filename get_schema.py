import sqlite3

conn = sqlite3.connect('E:/kiro-gateway/data/accounts.db')
cursor = conn.cursor()
cursor.execute('SELECT sql FROM sqlite_master WHERE type="table" AND name="sessions"')
result = cursor.fetchone()
print('Sessions table schema:')
print(result[0] if result else 'Table not found')
conn.close()
