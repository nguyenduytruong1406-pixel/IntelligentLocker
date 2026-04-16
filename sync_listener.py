import sqlite3
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
import time
#------------------------------------------------
#connection setup
#------------------------------------------------

# Initialize connections outside try block so finally can access them
#  khoi tao ben ngoai try de finally co the nhin thay
conn=None
try:
    # 1 Initialize Firebase
    cred = credentials.Certificate(r'D:/DATN/Software/test_db_ver1/private_key_lockers.json')
    firebase_admin.initialize_app(cred,{
        'databaseURL' : 'https://lockerxmakerspacexhcmute-default-rtdb.asia-southeast1.firebasedatabase.app'
    })
    print('[Cloud] Connected successfully!')

    # 2 Connect to sqlite
    conn = sqlite3.connect('D:/DATN/Software/test_db_ver1/IntelligentLocker.db', check_same_thread=False)
    cursor = conn.cursor()
    print("[Local] Database ready!")

# ----------------------------------------------------------------
# Event Handler Function
#------------------------------------------------------------------

    # This function triggers automatically whenever Firebase changes
    def on_firebase_change(event):
        print(f"\n [Alert] Firebase detected changes at path: {event.path}")
        # event.data contains the newdata ( chua du lieu moi)
        # event.path contains the changed path ( chua duong dan bi thay doi)

        

        # Skip if this is the initial connect event
        # Bo qua neu la su kien khoi tao ban dau(path="/")
        if event.path == '/':
            return
        try:
            ##Split the path to extract ID ( Cat dung duong dan de lay ID)
            mssv = event.path.split('/')[1]
            # Fetch the latest full data ( keo toan bo du lieu)
            user_data = db.reference(f'users/{mssv}').get()
            # Debug line to sê raw data
            print(f" [Debug] Raw data from Firebase: {user_data}")

            # Check if user exists and is approved
            if user_data is not None :
                name = user_data.get('name','Unknown')
                rfid = user_data.get('rfid', '')
                is_approved = user_data.get('is_approved',0)

                # Save to Sqlite
                command = "Insert or Replace into Users(name,mssv,rfid,is_approved) Values(?,?,?,?)"
                cursor.execute(command,(name,mssv,rfid,is_approved))
                conn.commit()

                # Smart print based on status
                status_text = "Approved (1)" if str(is_approved) == '1' else "Pending/Locked (0)"
                print(f"[Sync] Status: {status_text} | Student: {name} - ID: {mssv}")
            
            
            else:

                print(f"[Status] Student {mssv} is not approved yet or detected.")
        
        except Exception as e:
            print(f"[error] Failed to process data: {e}")
#------------------------------------------------------------------
# Start the listener
#---------------------------------------------------------------------

    # Point to the users node and start listening
    users_ref = db.reference('users')

    print("\n System is listening for Cloud updates...Press Ctrl+c to stop")
    # The listen() command keeps the program running continuously
    # Start listening
    listener =  users_ref.listen(on_firebase_change)

    # Keep the main program alive
    while True:
        time.sleep(1)

# Catch the event then user presses Ctrl+C to stop
except KeyboardInterrupt:
    print("\n [System] User interrupted the program. Shutting down...")

except Exception as e:
    print(f" [Error] System crashed: {e}")

# The block that Always runs at the end to clean up memory
finally:
    if conn:
        conn.close() # close SQLite safely
        print("[Local] SQLite connection closed safely.")