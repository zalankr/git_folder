with open("C:/Users/ilpus/Desktop/git_folder/Trading/CR_TR_Upbit/upnkr.txt") as f:
    access_key, secret_key = [line.strip() for line in f.readlines()]

print(access_key)
print(secret_key)