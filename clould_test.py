import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

try:
    # dẫn đường dẫn file json bảo mật cho file được quyền can thiệp vào database
    cred = credentials.Certificate(r'D:/DATN/Software/test_db_ver1/private_key_lockers.json')

    # Khởi tạo kết nối với database
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://lockerxmakerspacexhcmute-default-rtdb.asia-southeast1.firebasedatabase.app/'
    })
    print(" Connecting successfully Google Firebase")


    # Cursor drawer 5
    tu_so_5 = db.reference('lockers/L05')

    # Update status
    tu_so_5.update({
        'status': 'Occupied',
        'current_user_mssv': '22146436',
        'size': 'small'

    })
    print(" Day trang thai: Tu 5 len cloud")

    #Take all of data at branch number 5
    du_lieu = tu_so_5.get()

    print("Data is downloaded from cloud:")
    print(f" Status: {du_lieu.get('status')}")
    print(f" ID: {du_lieu.get('current_user_mssv')}")

except Exception as e:
    print(f" Have a problem: {e}")

