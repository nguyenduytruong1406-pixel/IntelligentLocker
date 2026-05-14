import sqlite3
try:
    conn=sqlite3.connect('D:/DATN/Software/test_db_ver1/IntelligentLocker.db')
    curser=conn.cursor()

    Name = "Nguyen Duy Truong"
    id = "22146436"

    command = "Insert into Users(name,mssv) Values(?,?)"

    curser.execute(command,(Name,id))
    #save
    conn.commit()
    print(f"Insert successfull information of student name: {Name} | mssv: {id}")

    #close conncecting
    conn.close()
except sqlite3.Error as er:
    print(f"Have a problem in your code: {er}")


