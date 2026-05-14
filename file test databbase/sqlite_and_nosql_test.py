import sqlite3
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

try:
    #đường dẫn file json private key
    cred = credentials.Certificate(r'D:/DATN/Software/test_db_ver1/private_key_lockers.json')

    #đường dẫn đến sqlite
    conn=sqlite3.connect('D:/DATN/Software/test_db_ver1/IntelligentLocker.db')

    #khoi tao ket noi
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://lockerxmakerspacexhcmute-default-rtdb.asia-southeast1.firebasedatabase.app/'
    })
    print("Connecting successfull Google Firebase")
    
    #tao con tro
    cursor=conn.cursor()

    #thong tin nguoi dung
    #cloud
    pers_1= db.reference('users/22146289')

    pers_1.update({
        'name': 'Ca Tan Duong',
        'rfid' : '98765',
        'role' : 'student',
        'is_approved': 0
    })
    print("Gui thong tin nguoi dung vua dang ky")
    #sqlite
    Name = "Ca Tan Duong"
    rfid = "98765"
    id = "22146289"

    command = "Insert into Users(name,mssv,rfid) Values(?,?,?)"

    cursor.execute(command,(Name,id,rfid))

    #save 
    conn.commit()

    print(f"Inser information for a newly registered student | name:{Name} | id:{id}")

    #close sqlite
    conn.close()

except Exception as e:
    print(f'errors at cloud{e}')

except sqlite3.Error as e:
    print(f'error at sqlite{e}')







                                   