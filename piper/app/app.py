from flask import Flask, request, render_template, send_file, url_for
import requests
from io import BytesIO
import os

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'  # Define a folder to save the uploaded files
port = 5500

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

@app.route('/', methods=['GET', 'POST'])
def index():
    wav_filename = None
    if request.method == 'POST':
        text = request.form['text']
        language = request.form['language']
        url = 'http://localhost:5501/' if language == 'EN' else 'http://localhost:5502/'

         # Replace line breaks with dots
        text = text.replace('\\r\\n', '.').replace('\\n', '.')

        # Send the text to the selected API endpoint as plain text
        response = requests.post(url, data=text.encode('utf-8'))

        if response.status_code == 200:
            wav_data = BytesIO(response.content)
            wav_filename = 'output.wav'
            wav_filepath = os.path.join(app.config['UPLOAD_FOLDER'], wav_filename)

            # Save the received WAV file to the uploads folder
            with open(wav_filepath, 'wb') as f:
                f.write(wav_data.read())
        else:
            return f"Error: Unable to process the request. Status code: {response.status_code}", response.status_code

    return render_template('index.html', wav_filename=wav_filename)

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename), as_attachment=True)

if __name__ == '__main__':
    app.run(port=port)
