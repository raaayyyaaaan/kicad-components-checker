import os
import sqlite3
import random
import pcbnew

def create_mock_database_from_kicad(kicad_pcb_path):
    db_name = "parts.db"
    
    if os.path.exists(db_name):
        os.remove(db_name)

    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE pcb_components (
            ref_des TEXT PRIMARY KEY,
            mpn TEXT,
            component_description TEXT,
            footprint TEXT,
            lifecycle_status TEXT
        )
    ''')

    try:
        board = pcbnew.LoadBoard(kicad_pcb_path)
    except Exception as e:
        print(f"Error loading KiCad board: {e}")
        return

    mock_parts = []
    
    mpn_status_cache = {}  
    status_pool = ["Approved", "Approved", "Approved", "NRND", "Obsolete"]
    for footprint in board.GetFootprints():
        ref_des = footprint.GetReference()
        val = footprint.GetValue()
        fp_name = str(footprint.GetFPID().GetLibItemName())
        
        clean_val = val.replace(" ", "_").upper()
        clean_fp = fp_name.replace(" ", "_").upper()
        mpn = f"RIV-{clean_val}-{clean_fp}"
        
        if mpn not in mpn_status_cache:
            mpn_status_cache[mpn] = random.choice(status_pool)
        
        lifecycle_status = mpn_status_cache[mpn]
        component_description = f"{val} automotive-grade surface mount component."

        mock_parts.append((
            ref_des,
            mpn,
            component_description,
            fp_name,
            lifecycle_status
        ))

    cursor.executemany('''
        INSERT INTO pcb_components (ref_des, mpn, component_description, footprint, lifecycle_status)
        VALUES (?, ?, ?, ?, ?)
    ''', mock_parts)
    
    conn.commit()
    conn.close()

    print(f"Successfully generated {db_name} with {len(mock_parts)} mock components mapping to your schema.")

if __name__ == "__main__":
    create_mock_database_from_kicad("mainboard-mini.kicad_pcb")