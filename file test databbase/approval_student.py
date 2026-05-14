import sqlite3
try:
    conn=sqlite3.connect('D:/DATN/Software/test_db_ver1/IntelligentLocker.db')
    curser=conn.cursor()

    id_student=22146436
    is_approved=1

    command="Update Users Set is_approved = ? Where mssv = ?"

    curser.execute(command,(is_approved,id_student))

    conn.commit()
    print(f"Update successfull status of student mssv: {id_student}")

    conn.close()
except sqlite3.Error as er:
    print(f"Have a problem in your code : {er}")
    


