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

def check_database(part_number: str) -> dict:
    try:
        with sqlite3.connect("parts.db") as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM approved_parts WHERE part_number = ?", (part_number,))
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
    components = [Component(**comp) for comp in raw_components]

    save_path = f"./uploaded_{board_file.filename}"
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(board_file.file, buffer)

    latest_board_filepath = save_path

    enriched_components = []
    for comp in components:
        db_record = check_database(comp.part_number)
        db_status = db_record["lifecycle_status"] if db_record else "Unknown"
        enriched_components.append({
            "ref_des": comp.ref_des,
            "value": comp.value,
            "part_number": comp.part_number,
            "db_status": db_status
        })

    system_prompt = """
    You are an expert PCB Layout AI Agent.
    Your job is to analyze a list of components and flag any violations based on company rules.

    COMPANY RULES:
    1. Flag any component whose db_status is "Obsolete", "Restricted", or "Unknown".
    2. Flag any power-filtering capacitor smaller than 0603 package size. You must infer this from the value/part_number if possible, or flag it if it appears suspicious.
    3. Provide a brief, technical explanation for any flagged component.

    Return a strict JSON object with a single key "flags", containing an array of objects.
    Each object must have:
    - "ref_des" (string)
    - "explanation" (string)
    
    If there are no violations, return an empty array for "flags".
    """

    user_prompt = f"Here is the component list:\n{json.dumps(enriched_components, indent=2)}"

    try:
        response = await client.aio.models.generate_content(
            
            # model='gemini-3.1-flash-lite', 
            # - best chances

            model='gemini-3.1-flash-lite-preview',
            # - mid chances

            # model= 'gemini-3-flash-preview', 
            # - lowest chances
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
        db_record = check_database(comp.part_number)
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

@app.get("/api/board_file")
async def get_board_file():
    if not latest_board_filepath or not os.path.exists(latest_board_filepath):
        raise HTTPException(status_code=404, detail="Board file not found. Run analysis first.")
        
    return FileResponse(board_path, media_type="application/octet-stream")

@app.get("/")
async def root():
    return FileResponse('dashboard.html')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)