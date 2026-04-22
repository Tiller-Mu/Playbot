import sqlite3, sys, os
db_path = 'server/workspace/data.db' 
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT p.full_path, c.title, c.script_content FROM test_cases c JOIN test_pages p ON c.page_id = p.id WHERE c.group_name='Automated' ORDER BY c.created_at DESC LIMIT 5")
for row in c.fetchall():
    print(f'Path: {row[0]} | Title: {row[1]}')
    print('Content:')
    print(row[2])
    print('---')
