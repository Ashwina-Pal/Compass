import sqlite3

def verify():
    conn = sqlite3.connect('compass.db')
    cursor = conn.cursor()
    
    # Check Diego's total data
    count = cursor.execute("SELECT COUNT(*) FROM checkins WHERE user_id = 'diego'").fetchone()[0]
    print(f"Diego's total records: {count}")
    
    # Check if rollup exists
    rollups = cursor.execute("SELECT * FROM archive_rollups WHERE user_id = 'diego'").fetchall()
    print(f"Number of rollups found: {len(rollups)}")
    
    if count < 30 and len(rollups) == 0:
        print("STATUS: FAILED - Not enough data for rollup.")
    else:
        print("STATUS: SUCCESS - Data is ready.")
    conn.close()

if __name__ == "__main__":
    verify()