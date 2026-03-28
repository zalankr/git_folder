import gspread

# 날짜 인풋 받기
year = 2026

## Google Spread sheet 작성
gc = gspread.service_account("C:/Users/ilpus/Desktop/NKL_invest/service_account.json")
# gc = gspread.service_account("C:/Users/ilpus/PythonProjects/US_Asset_Allocation/service_account.json")
# gc = gspread.service_account() #account 연결

# 기입 연도 스프레드시트 없으면 새로운 스프레드시트 만들기
filename = f"{year}_NKR_Account"

sh = gc.create(filename)
sh.share('ilpus0270@gmail.com', perm_type='user', role='writer')
   
mlist = ["Input","BAlance", "Portfolio", "Rule", "Future_KR", "Future_US", "ISA_IRP_Pension", "TAX", "Schedule"] 
for i in mlist :
    worksheet = sh.add_worksheet(title=f'{i}', rows=200, cols=100)

worksheet0 = sh.get_worksheet(0)
sh.del_worksheet(worksheet0)