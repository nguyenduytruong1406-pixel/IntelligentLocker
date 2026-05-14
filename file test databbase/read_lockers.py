import sqlite3
try:
    conn=sqlite3.connect('D:/DATN/Software/test_db_ver1/IntelligentLocker.db')
    curser=conn.cursor()
    print("Kết nối thành công với database")

    curser.execute("Select * From Lockers")
    danh_sach_tu=curser.fetchall()

    print("trạng thái ngăn tủ")

    if len(danh_sach_tu) ==0:
        print("chưa tìm thấy dữ liệu")

    else:
        for tu in danh_sach_tu:
            print(f" Ngăn số: {tu[0]} | Trạng thái: {tu[1]} | Loại: {tu[2]} ")

    # close connecting
    conn.close()

except sqlite3.Error as e:
    print(f" Have problem when connecting: {e}")
    print("You should check source file")




