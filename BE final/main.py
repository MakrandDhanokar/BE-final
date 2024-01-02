import os
import pickle
import datetime as dt_module
from datetime import datetime as dt_class
import time
import face_recognition
import numpy as np
from flask import Flask, render_template, Response, jsonify
import cv2
from flask import session
from flask import Flask, render_template, request, jsonify, redirect
import firebase_admin
from firebase_admin import credentials, db, storage

app = Flask(__name__)

app.secret_key = os.urandom(24)

# Initialize Firebase Admin SDK
cred = credentials.Certificate('E:/Learning/Deep Learning/Projects/BE final/serviceAccountKey.json')  # Replace with your service account key
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://attendance-a7527-default-rtdb.firebaseio.com/',  # Replace with your database URL
    'storageBucket': 'attendance-a7527.appspot.com'
})

camera = cv2.VideoCapture(0)

file = open("EncodeFile.p", "rb")
encodeListKnownWithIds = pickle.load(file)
file.close()
encodedFaceKnown, studentIDs = encodeListKnownWithIds


def mark_attendance(name):
    now = dt_class.now()
    dt_string = now.strftime('%d-%B-%Y')
    folder_name = "Attendance"
    filename = os.path.join(folder_name, dt_string + '.csv')

    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    if not os.path.exists(filename):
        with open(filename, 'w') as f:
            f.write('Name,Time,Total Time\n')

    with open(filename, 'r') as f:
        my_data_list = f.readlines()

    name_list = [line.strip().split(',')[0] for line in my_data_list]

    dt_string = now.strftime('%H:%M:%S')
    if name not in name_list:
        dt_string = now.strftime('%H:%M:%S')
        date = dt_class.now().strftime("%Y-%m-%d")
        employee_info = db.reference(f'Employee Attendance/{name}').get()
        ref = db.reference(f'Employee Attendance/{name}')
        employee_info['total_attendance'] += 1
        employee_info['last_attendance_time'] = f"{date} {dt_string}"
        ref.child('total_attendance').set(employee_info['total_attendance'])
        ref.child('last_attendance_time').set(employee_info['last_attendance_time'])

        with open(filename, 'a') as f:
            f.write(f'{name},{dt_string},0\n')
    else:
        index = name_list.index(name)
        info = my_data_list[index].strip().split(',')
        total_time = int(info[2]) + 5
        dt_string = info[1]
        my_data_list[index] = f'{name},{dt_string},{total_time}\n'

        with open(filename, 'w') as f:
                f.writelines(my_data_list)


def generate_frames():
    global encodedFaceKnown, camera

    detection_interval = 5  # Detection interval in seconds
    last_detection_time = time.time()

    while True:
        current_time = time.time()
        elapsed_time = current_time - last_detection_time

        success, frame = camera.read()
        if not success:
            break
        else:
            if elapsed_time >= detection_interval:
                imgSmall = cv2.resize(frame, (0, 0), None, 0.25, 0.25)
                imgSmall = cv2.cvtColor(imgSmall, cv2.COLOR_BGR2RGB)

                faceCurrentFrame = face_recognition.face_locations(imgSmall)
                encodeCurrentFrame = face_recognition.face_encodings(imgSmall, faceCurrentFrame)

                if faceCurrentFrame:
                    for encodeFace, faceLocation in zip(encodeCurrentFrame, faceCurrentFrame):
                        matches = face_recognition.compare_faces(encodedFaceKnown, encodeFace)
                        faceDistance = face_recognition.face_distance(encodedFaceKnown, encodeFace)

                        matchIndex = np.argmin(faceDistance)

                        if matches[matchIndex]:
                            id = studentIDs[matchIndex]
                            mark_attendance(id)

                last_detection_time = current_time

            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/video_feed')
def video_feed():

    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/attendance_data')
def attendance_data():
    current_time = time.time()
    dt_string = time.strftime('%d-%B-%Y')
    filename = os.path.join("Attendance", f"{dt_string}.csv")

    if os.path.exists(filename):
        with open(filename, 'r') as f:
            lines = f.readlines()
            html_table = '<table class="table table-bordered"><thead><tr><th>Name</th><th>Time</th><th>Total Time</th></tr></thead><tbody>'
            for line in lines[1:]:  # Skip the header line
                columns = line.strip().split(',')
                time_format = time.strftime("%H:%M:%S", time.gmtime(float(columns[2])))
                html_table += f'<tr><td>{columns[0]}</td><td>{columns[1]}</td><td>{time_format}</td></tr>'
            html_table += '</tbody></table>'
        return html_table
    else:
        return "No attendance data available for today."


@app.route('/login')
def login():
    return render_template('login.html')


@app.route('/validate_login', methods=['POST'])
def validate_login():
    id = request.form['id']
    password = request.form['password']

    ref = db.reference('Employee Attendance')  # Reference to the Firebase node

    user_data = ref.child(id).get()

    if user_data and user_data.get('password') == password:
        session['user_id'] = id  # Store the logged-in user ID in session
        return jsonify({'status': 'success'})
    else:
        return jsonify({'status': 'failure'})


@app.route('/login_admin')
def login_admin():
    return render_template('login_admin.html')

@app.route('/validate_admin_login', methods=['POST'])
def validate_admin_login():
    entered_username = request.form['id']
    entered_password = request.form['password']

    if entered_username == "admin" and entered_password == "admin":
        return redirect('/employee_cards')
    else:
        return "Invalid admin credentials! Please try again."

@app.route('/user_info')
def user_info():
    user_id = session.get('user_id')

    if user_id:
        ref = db.reference('Employee Attendance')
        user_details = ref.child(user_id).get()

        # Render the user_info.html template with user-specific data
        return render_template('info.html', user_details=user_details)
    else:
        return jsonify({'message': 'User not logged in'})


@app.route('/employee_cards')
def employee_cards():
    ref = db.reference('Employee Attendance')  # Reference to 'Employee Attendance' node
    employee_data = ref.get()  # Fetch employee details from Firebase Realtime Database

    if employee_data:
        for employee_id, employee_details in employee_data.items():
            bucket = storage.bucket()
            blob = bucket.get_blob(f'Images/{employee_id}.jpg')
            if blob:
                expiration = dt_module.timedelta(hours=1)
                signed_url = blob.generate_signed_url(expiration=expiration)
                employee_details['image_url'] = signed_url
            else:
                print(f"Image not found for {employee_id}")
                # Handle the case where the image doesn't exist

    return render_template('employee_cards.html', employee_data=employee_data)

@app.route('/user_info/<employee_id>')
def info(employee_id):
    ref = db.reference('Employee Attendance')
    employee_details = ref.child(employee_id).get()
    return render_template('info.html', user_details=employee_details)


if __name__ == "__main__":
    app.run(debug=True)
