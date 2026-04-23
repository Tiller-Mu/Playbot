import sqlite3
db_path = r'd:\dpProject\Playbot\workspace\data.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT latest_error_message FROM test_cases WHERE id = 'f0cf5fbc-aba1-47f1-b31b-2567e72742f5'")
row = cursor.fetchone()
if row: print('Latest Error:\n', row[0])
conn.close()
