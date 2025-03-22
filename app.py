from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from PIL import Image
import pytesseract
import os
import fitz  # PyMuPDF
from flask_cors import CORS
import io

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure Tesseract path (if needed)
# pytesseract.pytesseract.tesseract_cmd = r'<full_path_to_your_tesseract_executable>'

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'gif', 'tiff', 'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_image(image_path):
    img = Image.open(image_path)
    return pytesseract.image_to_string(img, lang='eng')

def process_pdf(pdf_path):
    text = []
    pdf_document = fitz.open(pdf_path)
    
    for page_num in range(len(pdf_document)):
        page = pdf_document.load_page(page_num)
        pix = page.get_pixmap()
        img_bytes = pix.tobytes('ppm')
        
        # Convert PPM image to PIL Image
        img = Image.open(io.BytesIO(img_bytes))
        
        # Perform OCR on the image
        page_text = pytesseract.image_to_string(img, lang='eng')
        text.append(page_text.strip())
    
    pdf_document.close()
    return '\n\n'.join(text)

@app.route('/extract-text', methods=['POST'])
def extract_text():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400

    try:
        # Save the uploaded file
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Process based on file type
        if filename.lower().endswith('.pdf'):
            extracted_text = process_pdf(filepath)
        else:
            extracted_text = process_image(filepath)

        # Clean up: remove the saved file
        os.remove(filepath)

        return jsonify({'text': extracted_text.strip()}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def health_check():
    return jsonify({'status': 'OCR API is running'}), 200

if __name__ == '__main__':
    # Create upload folder if it doesn't exist
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    
    app.run(debug=True, host='0.0.0.0', port=5000)