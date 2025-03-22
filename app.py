from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from PIL import Image
import pytesseract
import os
import fitz
from flask_cors import CORS
import io
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential

from dotenv import load_dotenv
load_dotenv()

token = os.getenv("GITHUB_TOKEN")

app = Flask(__name__)
CORS(app)

# Initialize Azure AI Client
client = ChatCompletionsClient(
    endpoint="https://models.inference.ai.azure.com",
    credential=AzureKeyCredential(token),
)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'gif', 'tiff', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_image(image_path):
    img = Image.open(image_path)
    return pytesseract.image_to_string(img, lang='eng')

def process_pdf(pdf_path):
    text = []
    pdf_document = fitz.open(pdf_path)
    for page_num in range(len(pdf_document)):
        page = pdf_document.load_page(page_num)
        pix = page.get_pixmap()
        img = Image.open(io.BytesIO(pix.tobytes('ppm')))
        text.append(pytesseract.image_to_string(img, lang='eng').strip())
    pdf_document.close()
    return '\n\n'.join(text)

def ask_llm(raw_text):
    try:
        response = client.complete(
            messages = [
    SystemMessage(content="""You are an advanced medical report analyzer with expertise in clinical documentation. 
    Your task is to extract and structure medical report data into a JSON format that strictly follows this schema:

    {
      "report_id": "Unique identifier for the medical report",
      "patient_info": {
        "patient_id": "Unique identifier for the patient",
        "name": "Full name of the patient",
        "date_of_birth": "Date of birth (YYYY-MM-DD)",
        "address": "Residential address"
      },
      "ordering_physician_info": {
        "physician_id": "Unique identifier for the physician",
        "name": "Physician’s full name",
        "contact_info": {
          "phone": "Physician's contact number",
          "email": "Physician's email address"
        }
      },
      "specimen_details": {
        "specimen_id": "Unique identifier for the specimen",
        "type": "Type of specimen collected (e.g., blood, urine, tissue)",
        "collection_datetime": "Timestamp of specimen collection (YYYY-MM-DD HH:MM:SS)",
        "collected_by": "Name of the person who collected the specimen"
      },
      "tests": [
        {
          "test_id": "Unique identifier for the test",
          "name": "Name of the test performed",
          "result": "Result of the test",
          "units": "Measurement units",
          "reference_range": "Normal range for the test",
          "flag": "Indicates if the result is normal, high, or low"
        }
      ],
      "interpretation": "Doctor’s interpretation of test results",
      "report_date": "Date of report generation (YYYY-MM-DD)",
      "laboratory_info": {
        "lab_id": "Unique identifier for the laboratory",
        "name": "Laboratory name",
        "address": "Laboratory address",
        "contact_info": {
          "phone": "Laboratory's contact number",
          "email": "Laboratory's email address"
        }
      }
    }

    Guidelines:
    - Ensure accurate extraction of patient, physician, specimen, and test details.
    - Convert dates and timestamps to ISO 8601 format (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
    - Ensure correct mapping of test results, units, and reference ranges.
    - Exclude any irrelevant information.
    - Maintain data privacy by excluding sensitive identifiers unless required by the schema.

    Output must be a **valid JSON object** adhering strictly to the schema.
    """),
    UserMessage(content=f"Structure this medical report:\n\n{raw_text}")
],

            model="gpt-4o",
    temperature=1,
    max_tokens=4096,
    top_p=1
        )
        return response.choices[0].message.content
    except Exception as e:
        return str(e)

@app.route('/extract-text', methods=['POST'])
def extract_text():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file'}), 400

    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Extract text
        raw_text = process_pdf(filepath) if filename.lower().endswith('.pdf') else process_image(filepath)
        
        # Get structured data from LLM
        structured_data = ask_llm(raw_text)
        
        os.remove(filepath)
        return jsonify({
            'raw_text': raw_text,
            'structured_data': structured_data
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def health_check():
    return jsonify({'status': 'API running'}), 200

if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(host='0.0.0.0', port=5000, debug=True)