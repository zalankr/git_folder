import gspread

# 날짜 인풋 받기
year = input('year?:')
model = input('model name?:')

## Google Spread sheet 작성
# gc = gspread.service_account("C:/Users/ilpus/Desktop/NKL_invest/service_account.json")
# gc = gspread.service_account("C:/Users/ilpus/PythonProjects/US_Asset_Allocation/service_account.json")
gc = gspread.service_account("/var/autobot/gspread/service_account.json") #account 연결

# 기입 연도 스프레드시트 없으면 새로운 스프레드시트 만들기
filename = f'{year}_{model}'

sh = gc.create(filename)
sh.share('ilpus0270@gmail.com', perm_type='user', role='writer')
   
mlist = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] 
for i in mlist :
    worksheet = sh.add_worksheet(title=f'{i}월', rows=80, cols=42)

worksheet0 = sh.get_worksheet(0)
sh.del_worksheet(worksheet0)
