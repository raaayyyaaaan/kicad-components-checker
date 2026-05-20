import sqlite3
import json
import os
from fastapi import FastAPI, HTTPException, Form, UploadFile, File
import shutil
from pydantic import BaseModel
from typing import List
from google import genai
from google.genai import types
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()
client = genai.Client()

app = FastAPI()

latest_analysis_results = []
latest_board_filepath = ""

class Component(BaseModel):
    ref_des: str
    value: str
    part_number: str
    x: float
    y: float

class AnalysisResult(BaseModel):
    component: Component
    status: str
    flagged: bool
    message: str

def check_database(ref_des: str) -> dict:
    try:
        with sqlite3.connect("parts.db") as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pcb_components WHERE ref_des = ?", (ref_des,))
            row = cursor.fetchone()
            
            return dict(row) if row else None
            
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return None

@app.post("/api/analyze", response_model=List[AnalysisResult])
async def analyze_components(
    components_data: str = Form(...), 
    board_file: UploadFile = File(...)
):
    global latest_analysis_results
    global latest_board_filepath

    raw_components = json.loads(components_data)

    save_path = f"./uploaded_{board_file.filename}"
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(board_file.file, buffer)

    latest_board_filepath = save_path

    components = []
    enriched_components = []
    db_cache = {}

    for comp in raw_components:
        ref_des = comp["ref_des"]
        db_record = check_database(ref_des)
        db_cache[ref_des] = db_record

        db_status = db_record["lifecycle_status"] if db_record else "Unknown"
        mpn = db_record["mpn"] if db_record else "Unknown"
        desc = db_record["component_description"] if db_record else ""

        comp_obj = Component(
            ref_des=ref_des,
            value=comp.get("value", ""),
            part_number=mpn, 
            x=comp.get("x", 0.0),
            y=comp.get("y", 0.0)
        )
        components.append(comp_obj)

        enriched_components.append({
            "ref_des": ref_des,
            "value": comp_obj.value,
            "part_number": mpn,
            "description": desc,
            "db_status": db_status,
            "x": comp_obj.x,
            "y": comp_obj.y
        })

    system_prompt = """
    You are an expert PCB Layout AI Agent for an EV company (like Rivian or Tesla).
    Your job is to analyze a list of components and flag violations based on strict company rules.

    COMPANY RULES:
    1. The AEC-Q Qualification Check: Flag any component that does not explicitly appear to be automotive grade based on its description, value, or part number. Note: "Standard commercial component used on critical net."
    2. The Lifecycle Check: You MUST flag any parts marked "NRND" (Not Recommended for New Designs) or "Obsolete" in their db_status. Do not just say it is bad; suggest an in-stock, "Approved" alternative of similar value/package.
    3. The Thermal/Clearance Check (Geometry): Analyze the X and Y coordinates. If any two components are suspiciously close to each other (e.g., < 3mm distance) and one appears to be a high-voltage/power component, flag a "High-Voltage IPC-2221 Clearance Violation" and cite their exact X/Y coordinates in your explanation.

    Return a strict JSON object with a single key "flags", containing an array of objects.
    Each object must have:
    - "ref_des" (string)
    - "explanation" (string)
    
    If there are no violations, return an empty array for "flags".
    """

    user_prompt = f"Here is the component list:\n{json.dumps(enriched_components, indent=2)}"

    try:
        response = await client.aio.models.generate_content(
            model='gemini-3.1-flash-lite-preview',
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.0
            )
        )
        llm_output = json.loads(response.text)
        flags_dict = {item["ref_des"]: item["explanation"] for item in llm_output.get("flags", [])}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM processing failed: {str(e)}")

    results = []
    for comp in components:
        is_flagged = comp.ref_des in flags_dict
        message = flags_dict.get(comp.ref_des, "Approved by AI agent.")
        
        db_record = db_cache.get(comp.ref_des)
        status = db_record["lifecycle_status"] if db_record else "Unknown"

        results.append(AnalysisResult(
            component=comp,
            status=status,
            flagged=is_flagged,
            message=message
        ))
        
    latest_analysis_results = results
    return results

@app.get("/api/results")
async def get_results():
    return latest_analysis_results

@app.get("/api/board_file/{filename}")
async def get_board_file(filename: str):
    if not latest_board_filepath or not os.path.exists(latest_board_filepath):
        raise HTTPException(status_code=404, detail="Board file not found. Run analysis first.")
    return FileResponse(latest_board_filepath, media_type="application/octet-stream")

@app.get("/")
async def root():
    return FileResponse('dashboard.html')

@app.get("/kicanvas.js")
async def get_kicanvas():
    if not os.path.exists("kicanvas.js"):
        raise HTTPException(status_code=404, detail="kicanvas.js not found in directory")
    return FileResponse('kicanvas.js', media_type='application/javascript')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)