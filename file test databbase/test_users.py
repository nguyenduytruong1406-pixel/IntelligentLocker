import sqlite3
try:

    conn=sqlite3.connect('D:/DATN/Software/test_db_ver1/IntelligentLocker.db')
    curser=conn.cursor()
    print("Successfull connecting!!!!!!")

    curser.execute("select * from Users")
    list_student=curser.fetchall()
    
    print("Status of list student register")
    if len(list_student) ==0:
        print(" data not found")

    else:
        for tu in list_student:
            print(f"ID: {tu[0]} | Name: {tu[1]} | MSSV: {tu[2]} | RFID: {tu[3]} | Role: {tu[4]} | Status: {tu[5]}")

    # close connecting *************important*************
    conn.close()

except sqlite3.Error as er:
    print(f"Have problems when connecting {er}")




