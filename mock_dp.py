import sqlite3
import os

def create_mock_database():
    db_name = "parts.db"
    if os.path.exists(db_name):
        os.remove(db_name)

    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    cursor.execute('''
                   CREATE TABLE approved_parts (
                        part_number TEXT PRIMARY KEY,
                        component_value TEXT,
                        footprint_size TEXT,
                        lifecycle_status TEXT
                   )
                   '''
                )
    # mock data
    mock_parts = [
        # valid parts
        ("RES-10k-0402", "10k Ohm", "0402", "Active"),
        ("RES-1k-0603", "1k Ohm", "0603", "Active"),
        ("CAP-100NF-0402", "100nF", "0402", "Active"),
        ("CAP-10UF-0805", "10uF", "0805", "Active"),
        ("IC-STM32G0B1", "STM32G0B1RT6", "LQFP-64", "Active"),

        #obsolete parts
        ("RES-4K7-0805", "4.7k Ohm", "0805", "Obsolete"),
        ("IC-ATMEGA328P", "ATMEGA328P-AU", "TQFP-32", "Obsolete"),

        #restricted parts
        ("CAP-22UF-1206", "22uF", "1206", "Restricted"),
        ("DIODE-1N4148", "1N4148WS", "SOD-323", "Restricted")
    ]

    cursor.executemany('''
                       INSERT INTO approved_parts (part_number, component_value, footprint_size, lifecycle_status)
                       VALUES (?, ?, ?, ?)
                    ''', mock_parts)
    conn.commit()
    conn.close()

    print(f"Successfully generated {db_name} with {len(mock_parts)} mock components")

if __name__ == "__main__":
    create_mock_database()
