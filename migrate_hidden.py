import sqlite3

# Path to DB
DB_PATH = "learning.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("Checking if column exists...")
        cursor.execute("SELECT is_hidden FROM courses LIMIT 1")
        print("Column 'is_hidden' already exists.")
    except sqlite3.OperationalError:
        print("Column missing. Adding 'is_hidden'...")
        cursor.execute("ALTER TABLE courses ADD COLUMN is_hidden BOOLEAN DEFAULT 0")
        conn.commit()
        print("Migration successful.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
