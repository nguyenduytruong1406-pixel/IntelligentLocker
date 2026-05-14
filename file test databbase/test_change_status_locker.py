import sqlite3
try:
    conn=sqlite3.connect('D:/DATN/Software/test_db_ver1/IntelligentLocker.db')
    curser=conn.cursor()
    #update status
    drawer_opened= 3
    new_status = 'Occupied'
    
    #command SQL update
    sql_command="UPDATE Lockers SET status = ? Where locker_id = ?"

    #Excecute command
    curser.execute(sql_command, (new_status, drawer_opened))

    #Save
    conn.commit()

    print(f"Updated successfully: Number drawer {drawer_opened} status {new_status}")

    #********Important***********
    #close connecting
    conn.close()

except sqlite3.Error as er:
    print(f"Have problems in your code: {er}")
