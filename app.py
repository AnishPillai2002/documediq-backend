from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from bson import ObjectId
from utils import (
    allowed_file, process_image, process_pdf, ask_llm,
    patients_collection, UPLOAD_FOLDER, reports_collection
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
        # Get patient_id and file_category from the request
        patient_id = request.form.get('patient_id')
        file_category = request.form.get('file_category')

        if not patient_id or not file_category:
            return jsonify({'error': 'patient_id and file_category are required'}), 400

        # Validate if the patient exists
        if not patients_collection.find_one({"_id": ObjectId(patient_id)}):
            return jsonify({'error': 'Patient not found'}), 404

        # Secure the filename and save the file
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save the file and wait for it to complete
        file.save(filepath)
        
        # Verify that the file exists and is not empty
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            return jsonify({'error': 'File upload failed or file is empty'}), 500

        # Extract text based on file type
        if filename.lower().endswith('.pdf'):
            raw_text = process_pdf(filepath)
        else:
            raw_text = process_image(filepath)
        
        # Get structured data from LLM
        structured_data = ask_llm(raw_text)
        
        # Save structured data to MongoDB
        report_data = {
            "patient_id": ObjectId(patient_id),  # Ensure patient_id is stored as ObjectId
            "file_category": file_category,
            "raw_text": raw_text,
            "structured_data": structured_data,
            "filename": filename,
        }
        reports_collection.insert_one(report_data)
        
        # Clean up: Remove the file after processing
        os.remove(filepath)
        
        return jsonify({
            'raw_text': raw_text,
            'structured_data': structured_data,
            'message': 'Report saved successfully'
        }), 200

    except Exception as e:
        # Clean up: Remove the file if an error occurs
        if os.path.exists(filepath):
            os.remove(filepath)
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
