# Upbit 토큰 불러오기
with open("C:/Users/ilpus/Desktop/NKL_invest/upnkr.txt") as f:
    access_key, secret_key = [line.strip() for line in f.readlines()]

print(access_key)
print(secret_key)