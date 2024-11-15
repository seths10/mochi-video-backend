from flask import Flask, json, request, jsonify, send_file
import subprocess
import os
from pathlib import Path
from typing import Tuple
from werkzeug.utils import secure_filename
import tempfile
import shutil

app = Flask(__name__)

@app.route('/api/home', methods=['GET'])
def return_home():
  return jsonify({
    'message': 'Hello World'
  })

@app.route('/api/add-voiceover', methods=['POST'])
def add_voiceover():
    if 'video' not in request.files:
        return jsonify({"error": "No video file provided"}), 400
    video_file = request.files['video']
    temp_dir = tempfile.mkdtemp()
    try:
        video_path = os.path.join(temp_dir, secure_filename(video_file.filename))
        video_file.save(video_path)
        audio_segments = []
        delays = []
        i = 0
        while f'audio_{i}' in request.files and f'delay_{i}' in request.form:
            audio_file = request.files[f'audio_{i}']
            audio_path = os.path.join(temp_dir, secure_filename(audio_file.filename))
            audio_file.save(audio_path)
            audio_segments.append(audio_path)
            delays.append(float(request.form[f'delay_{i}']))
            i += 1
        if not audio_segments:
            return jsonify({"error": "No audio segments provided"}), 400

        output_filename = f"processed_{secure_filename(video_file.filename)}"
        output_path = os.path.join(temp_dir, output_filename)
        filter_complex = []
        audio_inputs = []
        for i, (audio, delay) in enumerate(zip(audio_segments, delays)):
            delay_ms = int(float(delay) * 1000)
            filter_complex.append(f'[{i+1}:a]adelay={delay_ms}|{delay_ms}[a{i}]')
            audio_inputs.append(f'[a{i}]')
        if audio_inputs:
            filter_complex.append(f'{",".join(audio_inputs)}amix=inputs={len(audio_inputs)}[aout]')
        cmd = ['ffmpeg', '-y', '-i', video_path]
        for audio in audio_segments:
            cmd.extend(['-i', audio])
        if filter_complex:
            cmd.extend([
                '-filter_complex', ';'.join(filter_complex),
                '-map', '0:v',
                '-map', '[aout]'
            ])
        cmd.extend([
            '-c:v', 'copy',
            '-c:a', 'aac',
            output_path
        ])
        subprocess.run(cmd, check=True)

        if os.path.exists(output_path):
            response = send_file(
                output_path,
                mimetype='video/mp4',
                as_attachment=True,
                download_name=output_filename
            )

            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'

            return response
        else:
            return jsonify({"error": "Output file not found"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def escape_text(text: str) -> str:
    escaped = text.replace("'", "'\\\\''")
    escaped = escaped.replace(":", "\\:")
    return f"'{escaped}'"

def create_filter_string(text: str, start_time: float, duration: float, pos: Tuple[int, int]) -> str:
    return (
        f"drawtext=text={text}"
        f":fontfile=/Windows/Fonts/arial.ttf"
        f":fontsize=24"
        f":fontcolor=black"
        f":x={pos[0]}"
        f":y={pos[1]}"
        f":enable=between(t\\,{start_time}\\,{start_time + duration})"
        f":box=1"
        f":boxcolor=white@0.8"
        f":boxborderw=5"
    )

@app.route('/api/add-text-overlay', methods=['POST'])
def add_text_overlay():
    if 'video' not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    video_file = request.files['video']
    text_data_str = request.form.get('text_data')

    if not text_data_str:
        return jsonify({"error": "No text overlay data provided"}), 400

    try:
        text_data = json.loads(text_data_str)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid text overlay data format"}), 400

    temp_dir = tempfile.mkdtemp()
    try:
        video_path = os.path.join(temp_dir, secure_filename(video_file.filename))
        video_file.save(video_path)

        output_filename = f"text_overlay_{secure_filename(video_file.filename)}"
        output_path = os.path.join(temp_dir, output_filename)

        filter_complex = []
        for overlay in text_data:
            escaped_text = escape_text(overlay['text'])
            filter_str = create_filter_string(
                escaped_text,
                overlay['start_time'],
                overlay['duration'],
                overlay['position']
            )
            filter_complex.append(filter_str)

        filter_string = ','.join(filter_complex)

        video_path = str(Path(video_path).as_posix())
        output_path = str(Path(output_path).as_posix())

        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-vf', filter_string,
            '-c:a', 'copy',
            output_path
        ]

        result = subprocess.run(cmd, check=True, capture_output=True, text=True)

        if os.path.exists(output_path):
            response = send_file(
                output_path,
                mimetype='video/mp4',
                as_attachment=True,
                download_name=output_filename
            )

            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'

            return response
        else:
            return jsonify({"error": "Output file not found"}), 500

    except FileNotFoundError:
        return jsonify({"error": "FFmpeg not found. Please ensure FFmpeg is installed and accessible in your PATH"}), 500
    except subprocess.CalledProcessError as e:
        error_msg = f"FFmpeg error: {e.stderr if e.stderr else str(e)}"
        return jsonify({"error": error_msg}), 500
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == '__main__':
    app.run(port=5000)