from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from bson import ObjectId
from utils import (
    allowed_file, process_image, process_pdf, ask_llm,
    patients_collection, UPLOAD_FOLDER
)
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# Configuration
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit

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

@app.route('/add-patient', methods=['POST'])
def add_patient():
    try:
        patient_data = request.json
        if not patient_data:
            return jsonify({'error': 'No patient data provided'}), 400

        result = patients_collection.insert_one(patient_data)
        return jsonify({
            'message': 'Patient added successfully',
            'patient_id': str(result.inserted_id)
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get-patient/<patient_id>', methods=['GET'])
def get_patient(patient_id):
    try:
        patient = patients_collection.find_one({"_id": ObjectId(patient_id)})
        if not patient:
            return jsonify({'error': 'Patient not found'}), 404

        patient["_id"] = str(patient["_id"])
        return jsonify(patient), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get-all-patients', methods=['GET'])
def get_all_patients():
    try:
        patients = list(patients_collection.find({}))
        for patient in patients:
            patient["_id"] = str(patient["_id"])
        
        return jsonify(patients), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def health_check():
    return jsonify({'status': 'API running'}), 200

if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(host='0.0.0.0', port=5000, debug=True)
