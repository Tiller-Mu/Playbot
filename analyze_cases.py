import sqlite3
import json
import os

def get_data():
    conn = sqlite3.connect('workspace/data.db')
    cursor = conn.cursor()
    
    # 查找设置页面
    cursor.execute('SELECT id, file_path, full_path FROM test_pages WHERE full_path LIKE "%settings%" AND is_captured = 1 LIMIT 1')
    row = cursor.fetchone()
    if not row:
        print("Error: Settings page not found or not captured yet.")
        return
    
    page_id, file_path, full_path = row
    print(f"Analyzing Page: {full_path} (ID: {page_id})")
    print(f"Source File: {file_path}")
    
    # 获取用例
    cursor.execute('SELECT title, description, script_content FROM test_cases WHERE page_id = ? ORDER BY created_at DESC', (page_id,))
    cases = cursor.fetchall()
    
    print("\n" + "="*50)
    for i, (title, desc, code) in enumerate(cases):
        print(f"CASE #{i+1}: {title}")
        print(f"DESCRIPTION: {desc}")
        print("-" * 20)
        print("CODE:")
        print(code)
        print("="*50)
    
    conn.close()

if __name__ == "__main__":
    get_data()
